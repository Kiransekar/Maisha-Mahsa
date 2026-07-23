"""The scheduled job functions, with injected session / fake Mahsa / in-memory email."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.jobs as jobs_mod
from app.config import Settings
from app.core.email.channel import EmailChannel
from app.core.email.transport import InMemoryTransport
from app.core.mahsa_client import FoldResult, ResponseShape, Validation
from app.core.principal import current_org
from app.db.base import Base
from app.db.models.shared import JobRun, MetricSnapshot, Org
from app.domains import build_registry
from app.jobs import LEGACY_ORG, run_brief, run_capture, run_once


class _GreenMahsa:
    async def fold(
        self,
        snapshot: dict[str, Any],
        *,
        domain=None,
        query=None,
        rules_version=None,
        recompute_claims=None,
    ) -> FoldResult:
        return FoldResult(
            global_intent=[0.0],
            global_dims=["x"],
            validation=Validation(status="green"),
            shape=ResponseShape(
                status="green",
                color="green",
                layout="default",
                requires_approval=False,
                global_score=90.0,
            ),
            rules_version="rv",
        )


def test_capture_job_records_metrics(session: Session) -> None:
    res = run_capture(session, build_registry(), captured_at="2026-06-24", as_of=date(2026, 6, 24))
    assert res["job"] == "capture"
    assert res["metrics"] > 0


@pytest.mark.asyncio
async def test_brief_job_dispatches_via_transport(session: Session) -> None:
    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="cfo@maisha.local")
    res = await run_brief(
        session,
        _GreenMahsa(),
        build_registry(),
        channel,  # type: ignore[arg-type]
        to="founder@maisha.local",
        company_name="Maisha-Mahsa",
        as_of=date(2026, 6, 24),
    )
    assert res["job"] == "brief"
    assert res["overall_score"] == 90.0  # all domains green
    assert len(transport.sent) == 1
    assert transport.sent[0].to == "founder@maisha.local"


# --- WS4.5: tenant iteration — failure isolation + (org, job, period) idempotency -----------


NOW = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)


def _factory(*orgs: str) -> sessionmaker:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    if orgs:
        s = factory()
        for org in orgs:
            s.add(Org(id=org, name=org))
        s.commit()
        s.close()
    return factory


async def test_run_once_iterates_orgs_and_isolates_a_failing_tenant(monkeypatch) -> None:
    """One org's exception is recorded and the run CONTINUES — never aborts (WS4.5)."""
    factory = _factory("org-a", "org-b")
    seen: list[str | None] = []

    def fake_capture(session, registry, *, captured_at, as_of):
        seen.append(current_org())  # proves the org context was bound per tenant
        if current_org() == "org-a":
            raise RuntimeError("boom in org-a")
        return {"job": "capture", "captured_at": captured_at, "metrics": 1}

    monkeypatch.setattr(jobs_mod, "run_capture", fake_capture)
    res = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)

    assert seen == ["org-a", "org-b"]  # org-b still ran after org-a blew up
    assert res["summary"] == {
        "command": "capture",
        "period": "2026-07-22",
        "orgs": 2,
        "ok": 1,
        "failed": 1,
        "skipped": 0,
    }
    (err,) = [r for r in res["results"] if "error" in r]
    assert err["org"] == "org-a" and "boom" in err["error"]

    # the failed org is marked 'error' (retryable), the good one 'done'
    s = factory()
    runs = {r.org_id: r.status for r in s.scalars(select(JobRun)).all()}
    s.close()
    assert runs == {"org-a": "error", "org-b": "done"}


async def test_rerun_of_a_completed_period_is_a_noop(monkeypatch) -> None:
    """Idempotency keyed on (org, job, period): the second run writes NOTHING (WS4.5)."""
    factory = _factory("org-a")
    first = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)
    assert first["summary"]["ok"] == 1

    s = factory()
    rows_after_first = len(s.scalars(select(MetricSnapshot)).all())
    s.close()
    assert rows_after_first > 0

    second = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)
    assert second["summary"] == {
        "command": "capture",
        "period": "2026-07-22",
        "orgs": 1,
        "ok": 0,
        "failed": 0,
        "skipped": 1,
    }
    assert second["results"][0]["skipped"] == "already ran"

    s = factory()
    rows_after_second = len(s.scalars(select(MetricSnapshot)).all())
    s.close()
    assert rows_after_second == rows_after_first  # a re-run wrote no new metric rows

    # …but a NEW period runs again (the key is org+job+period, not org+job)
    next_day = datetime(2026, 7, 23, 20, 0, tzinfo=UTC)
    third = await run_once("capture", settings=Settings(), now_utc=next_day, factory=factory)
    assert third["summary"]["ok"] == 1 and third["summary"]["skipped"] == 0


async def test_an_error_run_does_not_block_the_retry(monkeypatch) -> None:
    factory = _factory("org-a")
    real_capture = jobs_mod.run_capture
    fail = {"on": True}

    def flaky_capture(session, registry, *, captured_at, as_of):
        if fail["on"]:
            raise RuntimeError("transient")
        return real_capture(session, registry, captured_at=captured_at, as_of=as_of)

    monkeypatch.setattr(jobs_mod, "run_capture", flaky_capture)
    first = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)
    assert first["summary"]["failed"] == 1

    fail["on"] = False  # retry within the SAME period must actually run, not skip
    second = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)
    assert second["summary"] == {
        "command": "capture",
        "period": "2026-07-22",
        "orgs": 1,
        "ok": 1,
        "failed": 0,
        "skipped": 0,
    }


async def test_no_orgs_falls_back_to_the_legacy_single_tenant_pass() -> None:
    """Empty orgs table on the SQLite dev path: the CLI contract is unchanged — one pass,
    recorded (and idempotent) under the 'default' org key."""
    factory = _factory()  # no orgs seeded
    res = await run_once("capture", settings=Settings(), now_utc=NOW, factory=factory)
    assert res["summary"]["orgs"] == 1 and res["summary"]["ok"] == 1
    assert res["results"][0]["org"] == LEGACY_ORG

    s = factory()
    (run,) = s.scalars(select(JobRun)).all()
    s.close()
    assert (run.org_id, run.job, run.period, run.status) == (
        LEGACY_ORG,
        "capture",
        "2026-07-22",
        "done",
    )
    assert json.dumps(res)  # the whole result is JSON-serializable for the CLI print


# --- MEM.P1-2: the per-org jobs thread the memory profile block (context only) --------------


async def test_brief_and_dunning_jobs_thread_the_org_memory_block(monkeypatch) -> None:
    """The brief and dunning closures fetch THIS org's profile block under the bound GUC and
    pass it down; the legacy single-tenant pass (no org identity) honestly passes none."""
    from app.db.models.memory import OrgMemory

    factory = _factory("org-a")
    s = factory()
    s.add(
        OrgMemory(
            org_id="org-a",
            kind="cfo_posture",
            content="- dunning tone: gentle",
            updated_at="2026-07-23T00:00:00+00:00",
            updated_by="owner",
        )
    )
    s.commit()
    s.close()

    seen: dict[str, str | None] = {}

    async def fake_brief(session, mahsa, registry, channel, *, memory=None, **kw):
        seen["brief"] = memory
        return {"job": "brief", "to": kw["to"], "needs_attention": 0, "overall_score": None}

    async def fake_dunning(self, session, as_of, channel, *, memory=None, **kw):
        seen["dunning"] = memory
        return {"as_of": str(as_of), "pending": 0, "sent": 0, "skipped_no_email": []}

    monkeypatch.setattr(jobs_mod, "run_brief", fake_brief)
    monkeypatch.setattr(jobs_mod.RevenueService, "dunning_run", fake_dunning)

    res = await run_once("brief", settings=Settings(), now_utc=NOW, factory=factory)
    assert res["summary"]["ok"] == 1
    res = await run_once("dunning", settings=Settings(), now_utc=NOW, factory=factory)
    assert res["summary"]["ok"] == 1

    for job in ("brief", "dunning"):
        block = seen[job]
        assert block is not None
        assert "dunning tone: gentle" in block
        assert "context only, NEVER a source of numbers" in block  # the verbatim label

    # Legacy single-tenant pass: no org identity -> no memory, never another org's.
    s = factory()
    assert jobs_mod._org_memory_block(s, None) is None
    assert "dunning tone: gentle" in (jobs_mod._org_memory_block(s, "org-a") or "")
    s.close()
