"""Scheduled jobs (PRD Layer 6): the daily snapshot capture (for trends) and the 8pm CFO brief.

Two ways to run, both using this module:
* cron-style — ``python -m app.jobs capture|brief|all`` runs once and exits (drive it from a
  crontab or any scheduler);
* long-lived — ``python -m app.jobs serve`` sleeps until the next configured local time and runs
  the jobs, forever (the ``scheduler`` service in docker-compose uses this).

Job functions take their session/mahsa/channel injected so they unit-test with an in-memory DB,
a fake Mahsa and ``InMemoryTransport`` — no network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

import app.db.models as _models  # noqa: F401  registers models on Base.metadata
from app.config import Settings, get_settings
from app.core import history_store
from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.cfo import collect_health, compose_brief
from app.core.email.channel import EmailChannel
from app.core.email.compose import compose_compliance_alert
from app.core.email.transport import smtp_from_settings
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.router import DomainRouter
from app.db.base import Base
from app.db.session import session_factory
from app.domains import build_registry
from app.domains.compliance.service import ComplianceService
from app.domains.revenue.service import RevenueService
from app.scheduler import seconds_until_next

_log = logging.getLogger("maisha.jobs")


def run_capture(
    session: Session, registry: DomainRouter, *, captured_at: str, as_of: date
) -> dict[str, Any]:
    """Capture every domain's numeric facts for the trend charts."""
    written = history_store.capture(session, registry, captured_at=captured_at, as_of=as_of)
    session.commit()
    return {"job": "capture", "captured_at": captured_at, "metrics": written}


async def run_brief(
    session: Session,
    mahsa: MahsaClient,
    registry: DomainRouter,
    channel: EmailChannel,
    *,
    to: str,
    company_name: str,
    as_of: date,
) -> dict[str, Any]:
    """Compose and dispatch the daily CFO Domain-Health brief."""
    health = await collect_health(session, mahsa, registry, as_of=as_of)
    brief = compose_brief(as_of.isoformat(), health)
    await channel.send_daily_brief(to=to, brief=brief, company_name=company_name)
    return {
        "job": "brief",
        "to": to,
        "needs_attention": len(brief.needs_attention),
        "overall_score": brief.overall_score,
    }


async def run_alerts(
    session: Session, channel: EmailChannel, *, to: str, as_of: date
) -> dict[str, Any]:
    """Dispatch statutory compliance alerts (T-7 / T-1 / T-0 / overdue) due as of ``as_of``."""
    alerts = ComplianceService().alerts(session, as_of)
    if not alerts:
        return {"job": "alerts", "dispatched": 0}
    ctx = compose_compliance_alert(alerts, as_of.isoformat())
    await channel.send_compliance_alert(to=to, ctx=ctx)
    return {"job": "alerts", "dispatched": len(alerts)}


def run_audit_verify(session: Session) -> dict[str, Any]:
    """Walk the hash-chained audit log and report integrity (P6-AUDITVERIFY)."""
    entries = load_chain(session)
    intact = verify_chain(entries)
    if not intact:
        _log.error("AUDIT CHAIN INTEGRITY FAILURE — %d entries, chain broken", len(entries))
    return {"job": "audit_verify", "intact": intact, "entries": len(entries)}


async def run_once(command: str, *, settings: Settings, now_utc: datetime) -> dict[str, Any]:
    """Run a job once with real wiring. Failures are caught and reported, never raised, so a
    scheduler tick never crashes the loop."""
    registry = build_registry()
    today = now_utc.date()
    factory = session_factory()
    Base.metadata.create_all(bind=factory.kw["bind"])  # self-sufficient: ensure schema exists
    session = factory()
    results: list[dict[str, Any]] = []
    try:
        if command in ("capture", "all"):
            try:
                results.append(
                    run_capture(session, registry, captured_at=today.isoformat(), as_of=today)
                )
            except Exception as exc:  # noqa: BLE001 - report, don't crash the scheduler
                _log.exception("capture job failed")
                results.append({"job": "capture", "error": str(exc)})
        if command in ("brief", "all"):
            channel = EmailChannel(
                smtp_from_settings(settings),
                sender=settings.email_sender,
            )
            try:
                results.append(
                    await run_brief(
                        session,
                        MahsaClient(settings.mahsa_url),
                        registry,
                        channel,
                        to=settings.cfo_email,
                        company_name=settings.app_name,
                        as_of=today,
                    )
                )
            except (MahsaError, OSError) as exc:
                _log.warning("brief job skipped: %s", exc)
                results.append({"job": "brief", "error": str(exc)})
        if command in ("dunning", "all"):
            channel = EmailChannel(
                smtp_from_settings(settings),
                sender=settings.email_sender,
            )
            try:
                summary = await RevenueService().dunning_run(
                    session, today, channel, company_name=settings.app_name
                )
                results.append({"job": "dunning", **summary})
            except OSError as exc:
                _log.warning("dunning job skipped: %s", exc)
                results.append({"job": "dunning", "error": str(exc)})
        if command in ("alerts", "all"):
            channel = EmailChannel(
                smtp_from_settings(settings),
                sender=settings.email_sender,
            )
            try:
                results.append(
                    await run_alerts(session, channel, to=settings.cfo_email, as_of=today)
                )
            except OSError as exc:
                _log.warning("alerts job skipped: %s", exc)
                results.append({"job": "alerts", "error": str(exc)})
        if command in ("audit-verify", "all"):
            try:
                results.append(run_audit_verify(session))
            except Exception as exc:  # noqa: BLE001 - report, don't crash the scheduler
                _log.exception("audit-verify job failed")
                results.append({"job": "audit_verify", "error": str(exc)})
    finally:
        session.close()
    return {"ran": command, "at": now_utc.isoformat(), "results": results}


async def serve(settings: Settings) -> None:  # pragma: no cover - long-running loop
    """Sleep until the next configured local time, run capture+brief, repeat."""
    _log.info(
        "scheduler up — daily jobs at %02d:%02d %s",
        settings.brief_hour,
        settings.brief_minute,
        settings.brief_tz,
    )
    while True:
        delay = seconds_until_next(
            datetime.now(UTC),
            hour=settings.brief_hour,
            minute=settings.brief_minute,
            tz=settings.brief_tz,
        )
        await asyncio.sleep(delay)
        result = await run_once("all", settings=settings, now_utc=datetime.now(UTC))
        _log.info("daily jobs ran: %s", json.dumps(result))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="app.jobs", description="Maisha scheduled jobs")
    parser.add_argument(
        "command",
        choices=["capture", "brief", "dunning", "alerts", "audit-verify", "all", "serve"],
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "serve":
        asyncio.run(serve(settings))
        return 0
    result = asyncio.run(run_once(args.command, settings=settings, now_utc=datetime.now(UTC)))
    print(json.dumps(result))
    return 0 if all("error" not in r for r in result["results"]) else 1


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
