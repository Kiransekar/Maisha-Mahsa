"""Scheduled jobs (PRD Layer 6): the daily snapshot capture (for trends) and the 8pm CFO brief.

Two ways to run, both using this module:
* cron-style — ``python -m app.jobs capture|brief|evolve|all`` runs once and exits (drive it
  from a crontab or any scheduler); ``all`` includes the nightly memory ``evolve``
  (MEM.P1-1), so the standard daily cron line below already runs it;
* long-lived — ``python -m app.jobs serve`` sleeps until the next configured local time and runs
  the jobs, forever (the ``scheduler`` service in docker-compose uses this).

Tenant iteration (WS4.5)
------------------------
Every job iterates the ``orgs`` table with:

* **per-tenant failure isolation** — one org's exception is logged and recorded in the run
  results; the run CONTINUES to the next org, and one summary line is logged per run;
* **idempotency** — a ``job_run`` row keyed on ``(org, job, period)`` makes a re-run for a
  period the job already completed a NO-OP (an ``error`` row does not block the retry);
* **org scoping** — each org's work runs with that org bound to the RLS GUC, the same
  mechanism the API uses (``app.core.principal``); a no-op on SQLite, row-filtering on
  Postgres.

When the ``orgs`` table is empty on the SQLite dev path, the run falls back to the legacy
single-tenant pass (recorded as org ``default``), so the CLI contract is unchanged. On
Postgres, jobs run ONLY for rows in ``orgs``.

External cron (all config via env, prefix ``MAISHA_`` — see ``app/config.py`` Settings)::

    # m h dom mon dow
    0 20 * * *  cd /srv/maisha && .venv/bin/python -m app.jobs all

Required env: ``MAISHA_DATABASE_URL`` (on Postgres point it at the tenant schema, e.g.
``...?options=-csearch_path%3Dtenant_core,public``, with a role permitted to enumerate
``orgs``); ``MAISHA_MAHSA_URL`` for ``brief``; ``MAISHA_CFO_EMAIL`` + ``MAISHA_SMTP_HOST`` /
``MAISHA_SMTP_PORT`` / ``MAISHA_EMAIL_SENDER`` for ``brief``/``dunning``/``alerts``.
Exit code: 0 when no job errored (idempotent skips are NOT errors, so a same-day cron re-run
exits 0), 1 otherwise.

Job functions take their session/mahsa/channel injected so they unit-test with an in-memory DB,
a fake Mahsa and ``InMemoryTransport`` — no network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.models as _models  # noqa: F401  registers models on Base.metadata
from app.config import Settings, get_settings
from app.core import history_store, memory
from app.core.audit import verify_chain
from app.core.audit_store import load_chain, load_chain_for, verify_chain_for
from app.core.cfo import collect_health, compose_brief
from app.core.email.channel import EmailChannel
from app.core.email.compose import compose_compliance_alert
from app.core.email.transport import smtp_from_settings
from app.core.mahsa_client import MahsaClient
from app.core.principal import bind_org_guc, reset_current_org, set_current_org
from app.core.router import DomainRouter
from app.db.base import Base
from app.db.models.memory import OrgMemory
from app.db.models.shared import JobRun, Org
from app.db.session import session_factory
from app.domains import build_registry
from app.domains.compliance.service import ComplianceService
from app.domains.revenue.service import RevenueService
from app.scheduler import seconds_until_next

_log = logging.getLogger("maisha.jobs")

#: Org key recorded for the legacy single-tenant pass (SQLite dev, empty ``orgs`` table).
LEGACY_ORG = "default"


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


def run_evolve(session: Session, org: str | None, *, now: str) -> dict[str, Any]:
    """Nightly memory evolution (MEM.P1-1): :func:`app.core.memory.evolve` — deterministic
    re-consolidation of the org's CFO block (archive-on-supersede + ``memory.update`` seal,
    exactly like the API write path, attributed to ``system:evolve``) and the bounded
    history prune. Idempotent twice over: the (org, job, period) ledger makes a same-day
    re-run a no-op before this is even called, and evolve itself finds nothing to change on
    a second pass. On the legacy single-tenant pass (``org=None``) it walks every org that
    actually has memory rows."""
    org_ids: list[str] = (
        [org] if org is not None else sorted(session.scalars(select(OrgMemory.org_id).distinct()))
    )
    consolidated = 0
    pruned = 0
    for oid in org_ids:
        out = memory.evolve(session, oid, now=now)
        consolidated += int(out["consolidated"])
        pruned += out["history_pruned"]
    session.commit()
    return {
        "job": "evolve",
        "memory_orgs": len(org_ids),
        "consolidated": consolidated,
        "history_pruned": pruned,
    }


def run_audit_verify(session: Session, org: str | None = None) -> dict[str, Any]:
    """Walk the hash-chained audit log and report integrity (P6-AUDITVERIFY).

    With an ``org``, only that tenant's independent chain is walked (WS4.4); without one,
    the legacy global chain."""
    if org is None:
        entries = load_chain(session)
        intact = verify_chain(entries)
    else:
        entries = load_chain_for(session, org)
        intact = verify_chain_for(session, org)
    if not intact:
        _log.error("AUDIT CHAIN INTEGRITY FAILURE — %d entries, chain broken", len(entries))
    return {"job": "audit_verify", "intact": intact, "entries": len(entries)}


# --- WS4.5 tenant iteration: org discovery, idempotency ledger, per-org dispatch -----------


def _org_ids(session: Session, dialect: str) -> list[str | None]:
    """Orgs to iterate. Empty ``orgs`` table: on Postgres → nothing to do (tenant path only);
    on SQLite dev → one legacy single-tenant pass (``None`` → recorded as ``LEGACY_ORG``)."""
    ids: list[str | None] = list(session.scalars(select(Org.id).order_by(Org.id)))
    if ids:
        return ids
    return [] if dialect == "postgresql" else [None]


def _already_done(session: Session, org_key: str, job: str, period: str) -> bool:
    row = session.scalars(
        select(JobRun).where(
            JobRun.org_id == org_key, JobRun.job == job, JobRun.period == period
        )
    ).first()
    return row is not None and row.status == "done"


def _mark(
    session: Session, org_key: str, job: str, period: str, status: str, ran_at: str
) -> None:
    row = session.scalars(
        select(JobRun).where(
            JobRun.org_id == org_key, JobRun.job == job, JobRun.period == period
        )
    ).first()
    if row is None:
        row = JobRun(org_id=org_key, job=job, period=period, status=status, ran_at=ran_at)
        session.add(row)
    else:
        row.status = status
        row.ran_at = ran_at
    session.commit()


def _ensure_org_guc(engine: Engine) -> None:
    """Install the same RLS GUC re-bind ``app.main`` puts on the API engine — the cron path
    never imports ``app.main``, so without this a Postgres jobs run would query unscoped."""
    if getattr(engine, "_maisha_org_guc", False):
        return
    engine._maisha_org_guc = True  # type: ignore[attr-defined]

    @event.listens_for(engine, "checkout")
    def _rebind(dbapi_conn: object, _record: object, _proxy: object) -> None:
        bind_org_guc(dbapi_conn, engine.dialect.name)


async def _run_org(
    command: str,
    session: Session,
    settings: Settings,
    registry: DomainRouter,
    *,
    org: str | None,
    today: date,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    """All requested jobs for ONE org — each idempotent and individually caught, so one job's
    failure never takes down the others (and never the run)."""
    org_key = org or LEGACY_ORG
    period = today.isoformat()
    results: list[dict[str, Any]] = []

    async def guarded(name: str, runner: Callable[[], Awaitable[dict[str, Any]]]) -> None:
        if _already_done(session, org_key, name, period):
            results.append(
                {"job": name, "org": org_key, "period": period, "skipped": "already ran"}
            )
            return
        try:
            out = await runner()
        except Exception as exc:  # noqa: BLE001 — isolation: report, mark, continue
            _log.exception("%s job failed org=%s", name, org_key)
            session.rollback()
            _mark(session, org_key, name, period, "error", now_utc.isoformat())
            results.append({"job": name, "org": org_key, "error": str(exc)})
            return
        _mark(session, org_key, name, period, "done", now_utc.isoformat())
        results.append({**out, "org": org_key})

    def channel() -> EmailChannel:
        return EmailChannel(smtp_from_settings(settings), sender=settings.email_sender)

    if command in ("capture", "all"):

        async def _capture() -> dict[str, Any]:
            return run_capture(session, registry, captured_at=period, as_of=today)

        await guarded("capture", _capture)
    if command in ("brief", "all"):

        async def _brief() -> dict[str, Any]:
            return await run_brief(
                session,
                MahsaClient(settings.mahsa_url),
                registry,
                channel(),
                to=settings.cfo_email,
                company_name=settings.app_name,
                as_of=today,
            )

        await guarded("brief", _brief)
    if command in ("dunning", "all"):

        async def _dunning() -> dict[str, Any]:
            summary = await RevenueService().dunning_run(
                session, today, channel(), company_name=settings.app_name
            )
            return {"job": "dunning", **summary}

        await guarded("dunning", _dunning)
    if command in ("alerts", "all"):

        async def _alerts() -> dict[str, Any]:
            return await run_alerts(session, channel(), to=settings.cfo_email, as_of=today)

        await guarded("alerts", _alerts)
    if command in ("evolve", "all"):

        async def _evolve() -> dict[str, Any]:
            return run_evolve(session, org, now=now_utc.isoformat())

        await guarded("evolve", _evolve)
    if command in ("audit-verify", "all"):

        async def _audit() -> dict[str, Any]:
            return run_audit_verify(session, org)

        await guarded("audit_verify", _audit)
    return results


async def run_once(
    command: str,
    *,
    settings: Settings,
    now_utc: datetime,
    factory: sessionmaker[Session] | None = None,
) -> dict[str, Any]:
    """Run the requested job(s) once for EVERY org, with per-tenant failure isolation and
    per-(org, job, period) idempotency. Failures are caught and reported, never raised, so a
    scheduler tick never crashes the loop. ``factory`` is injectable for tests."""
    registry = build_registry()
    today = now_utc.date()
    factory = factory or session_factory()
    engine: Engine = factory.kw["bind"]
    Base.metadata.create_all(bind=engine)  # self-sufficient: ensure schema exists
    _ensure_org_guc(engine)

    probe = factory()
    try:
        orgs = _org_ids(probe, engine.dialect.name)
    finally:
        probe.close()

    results: list[dict[str, Any]] = []
    for org in orgs:
        token = set_current_org(org)  # RLS-scopes this org's work on Postgres (§0.8)
        session = factory()
        try:
            results.extend(
                await _run_org(
                    command, session, settings, registry,
                    org=org, today=today, now_utc=now_utc,
                )
            )
        except Exception as exc:  # noqa: BLE001 — per-tenant isolation at the org level too
            _log.exception("org run failed org=%s", org or LEGACY_ORG)
            results.append({"job": command, "org": org or LEGACY_ORG, "error": str(exc)})
        finally:
            session.close()
            reset_current_org(token)

    summary = {
        "command": command,
        "period": today.isoformat(),
        "orgs": len(orgs),
        "ok": sum(1 for r in results if "error" not in r and "skipped" not in r),
        "failed": sum(1 for r in results if "error" in r),
        "skipped": sum(1 for r in results if "skipped" in r),
    }
    _log.info("jobs summary: %s", json.dumps(summary))  # the one summary line per run
    return {"ran": command, "at": now_utc.isoformat(), "summary": summary, "results": results}


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
        choices=["capture", "brief", "dunning", "alerts", "evolve", "audit-verify", "all", "serve"],
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
