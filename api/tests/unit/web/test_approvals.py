"""F4 approvals: the queue surfaces Mahsa-flagged domains; a decision is sealed onto the audit
chain + recorded, and resolves the item until the books change."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import decision_store
from app.core.approvals import pending_approvals, record_decision
from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.mahsa_client import FoldResult, ResponseShape, TriggeredRule, Validation
from app.db.models.shared import Decision
from app.domains import build_registry


def _fold(requires_approval: bool, triggered: list[TriggeredRule]) -> FoldResult:
    status = "red" if triggered else "green"
    return FoldResult(
        global_intent=[0.0],
        global_dims=["x"],
        validation=Validation(status=status, triggered=triggered),
        shape=ResponseShape(
            status=status,
            color=status,
            layout="default",
            requires_approval=requires_approval,
            global_score=60.0,
        ),
        rules_version="rv1",
    )


class _FakeMahsa:
    """Flags only the gst domain for approval; everything else is clean."""

    async def fold(
        self,
        snapshot: dict[str, Any],
        *,
        domain=None,
        query=None,
        rules_version=None,
        recompute_claims=None,
    ) -> FoldResult:
        if domain == "gst":
            rule = TriggeredRule(
                id="GST-001",
                domain="gst",
                severity="block",
                description="GSTR-3B overdue",
                statute="CGST Act 2017",
                section="Sec 47 / Rule 61",
                action="file",
            )
            return _fold(True, [rule])
        return _fold(False, [])


@pytest.mark.asyncio
async def test_pending_lists_only_flagged_domains(session: Session) -> None:
    items = await pending_approvals(session, _FakeMahsa(), build_registry())  # type: ignore[arg-type]
    assert [i.domain for i in items] == ["gst"]
    assert items[0].resolution is None
    assert items[0].citations[0]["rule_id"] == "GST-001"


@pytest.mark.asyncio
async def test_decision_seals_audit_and_resolves(session: Session) -> None:
    registry = build_registry()
    mahsa = _FakeMahsa()
    msg = await record_decision(
        session,
        domain="gst",
        decision="approved",
        mahsa=mahsa,  # type: ignore[arg-type]
        registry=registry,
        as_of=date(2026, 7, 10),
        timestamp="2026-07-10T20:00:00",
    )
    assert "approved" in msg.lower()

    # an audit entry was sealed and the chain still verifies
    chain = load_chain(session)
    assert chain[-1].action == "approval.approved"
    assert chain[-1].domain == "gst"
    assert verify_chain(chain) is True

    # a Decision row exists and the item is now resolved
    rows = session.scalars(select(Decision)).all()
    assert len(rows) == 1 and rows[0].decision == "approved"

    items = await pending_approvals(session, mahsa, registry, as_of=date(2026, 7, 10))  # type: ignore[arg-type]
    assert items[0].resolution == "approved"  # same state_hash -> resolved


@pytest.mark.asyncio
async def test_record_decision_rejects_bad_value(session: Session) -> None:
    with pytest.raises(ValueError):
        await record_decision(
            session,
            domain="gst",
            decision="maybe",
            mahsa=_FakeMahsa(),  # type: ignore[arg-type]
            registry=build_registry(),
        )


def test_decision_store_resolution_keyed_by_state(session: Session) -> None:
    decision_store.append(
        session,
        timestamp="t",
        domain="gst",
        decision="approved",
        state_hash="hashA",
        audit_hash="a",
        user_id="founder",
    )
    assert decision_store.resolution(session, "gst", "hashA") == "approved"
    assert decision_store.resolution(session, "gst", "hashB") is None  # different state = pending
