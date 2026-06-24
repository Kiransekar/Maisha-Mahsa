"""run_loop's optional drafting step: when a generator is supplied the claim is attached to
the outcome; Mahsa still folds the deterministic snapshot (Golden Rule). With no generator the
loop is unchanged. Uses a fake Mahsa + fake service so there is no network or binary."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService, DomainManifest
from app.core.loop import run_loop
from app.core.mahsa_client import FoldResult, ResponseShape, Validation
from app.db.models.shared import LlmTrace
from app.llm.client import CannedClient
from app.llm.maisha import MaishaGenerator


class _FakeService(BaseDomainService):
    domain = "treasury"
    manifest = DomainManifest(domain="treasury", features=[])

    def build_snapshot(self, session: Session) -> dict[str, Any]:
        return {"cash": 120000000, "monthly_burn": 30000000, "monthly_revenue": 10000000}


class _FakeMahsa:
    async def fold(
        self, snapshot: dict[str, Any], *, domain: str | None = None, query: str | None = None
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
                global_score=100.0,
            ),
            rules_version="test",
        )


@pytest.mark.asyncio
async def test_run_loop_attaches_claim_when_generator_supplied(session: Session) -> None:
    canned = CannedClient({"domain": "treasury", "claims": {"cash": "120000000"}})
    gen = MaishaGenerator(canned)
    outcome = await run_loop(
        session=session,
        mahsa=_FakeMahsa(),  # type: ignore[arg-type]
        service=_FakeService(),
        timestamp="2026-06-24T20:00:00",
        query="What's our runway?",
        generator=gen,
    )
    assert outcome.claim is not None
    assert outcome.claim.domain == "treasury"
    assert outcome.claim.claims["cash"] == "120000000"  # backed by the snapshot fact
    assert outcome.claim_verified is True
    assert outcome.requires_approval is False
    assert outcome.fold.validation.status == "green"


@pytest.mark.asyncio
async def test_run_loop_falls_back_and_requires_approval_on_unbacked_number(
    session: Session,
) -> None:
    # The model keeps inventing a number not in the facts → exhausts retries → fact-built
    # fallback, flagged for approval. The Golden Rule holds: no unbacked number ships.
    canned = CannedClient({"domain": "treasury", "claims": {"cash": "999"}})
    outcome = await run_loop(
        session=session,
        mahsa=_FakeMahsa(),  # type: ignore[arg-type]
        service=_FakeService(),
        timestamp="2026-06-24T20:00:00",
        query="What's our runway?",
        generator=MaishaGenerator(canned),
        max_retries=1,
    )
    assert outcome.claim_verified is False
    assert outcome.requires_approval is True
    assert "999" not in outcome.claim.claims.values()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_run_loop_writes_llm_trace(session: Session) -> None:
    canned = CannedClient({"domain": "treasury", "claims": {"cash": "120000000"}})
    gen = MaishaGenerator(canned, label="ollama:qwen3:14b")
    outcome = await run_loop(
        session=session,
        mahsa=_FakeMahsa(),  # type: ignore[arg-type]
        service=_FakeService(),
        timestamp="2026-06-24T20:00:00",
        query="runway?",
        generator=gen,
    )
    rows = session.scalars(select(LlmTrace)).all()
    assert len(rows) == 1
    trace = rows[0]
    assert trace.model_label == "ollama:qwen3:14b"
    assert trace.domain == "treasury"
    assert trace.audit_hash == outcome.audit_hash  # linked to the audit entry
    assert trace.verified == 1
    assert trace.attempts == 1
    assert len(trace.input_sha256) == 64 and trace.claim_sha256 is not None
    assert trace.latency_ms >= 0  # wall-clock of the draft step captured


@pytest.mark.asyncio
async def test_run_loop_writes_no_trace_without_generator(session: Session) -> None:
    await run_loop(
        session=session,
        mahsa=_FakeMahsa(),  # type: ignore[arg-type]
        service=_FakeService(),
        timestamp="2026-06-24T20:00:00",
        query="runway?",
    )
    assert session.scalars(select(LlmTrace)).all() == []


@pytest.mark.asyncio
async def test_run_loop_without_generator_is_unchanged(session: Session) -> None:
    outcome = await run_loop(
        session=session,
        mahsa=_FakeMahsa(),  # type: ignore[arg-type]
        service=_FakeService(),
        timestamp="2026-06-24T20:00:00",
        query="What's our runway?",
    )
    assert outcome.claim is None
