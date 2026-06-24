"""Ask Maisha orchestrator: assembles a verified Answer from facts + Mahsa fold + LLM draft,
and degrades cleanly when a domain can't be classified."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.ask import answer_query
from app.core.mahsa_client import FoldResult, ResponseShape, TriggeredRule, Validation
from app.db.models.gst import GstReturn
from app.domains import build_registry
from app.llm.schema import ActionClaim

_SETTINGS = SimpleNamespace(
    mahsa_url="http://unused", llm_provider="off", llm_max_retries=2,
    ollama_model="m", claude_model="c",
)


class _FakeMahsa:
    def __init__(self, triggered: list[TriggeredRule]) -> None:
        self._t = triggered

    async def fold(self, snapshot: dict[str, Any], *, domain=None, query=None) -> FoldResult:
        status = "red" if self._t else "green"
        return FoldResult(
            global_intent=[0.0], global_dims=["x"],
            validation=Validation(status=status, triggered=self._t),
            shape=ResponseShape(
                status=status, color=status, layout="default",
                requires_approval=bool(self._t), global_score=70.0,
            ),
            rules_version="test",
        )


class _CannedGen:
    label = "test:model"

    def __init__(self, claim: ActionClaim) -> None:
        self._claim = claim

    async def produce(  # noqa: ANN001
        self, *, snapshot, query, domain, case_id="", feedback=None
    ) -> ActionClaim:
        return self._claim


def _seed_late_gst(session: Session) -> None:
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-05",
            due_date="2026-06-20",
            status="pending",
        )
    )
    session.flush()


@pytest.mark.asyncio
async def test_answer_query_verified_with_citation(session: Session) -> None:
    _seed_late_gst(session)
    registry = build_registry()
    rule = TriggeredRule(
        id="GST-001", domain="gst", severity="block", description="GSTR-3B overdue",
        statute="CGST Act 2017", section="Sec 47 / Rule 61", action="file",
    )
    # claim restates a backed fact (days late = 20 as of 2026-07-10 is what build_snapshot gives,
    # but we fold/produce against the seeded snapshot whose value the generator must match)
    # as_of 2026-07-10 → snapshot says 20 days late, so the claim's "20" is a backed fact.
    claim = ActionClaim(domain="gst", narrative="Overdue.", claims={"gstr3b_days_late": "20"})
    gen = _CannedGen(claim)
    answer = await answer_query(
        session, query="is our gstr-3b on time?", registry=registry, settings=_SETTINGS,
        as_of=date(2026, 7, 10), mahsa=_FakeMahsa([rule]), generator=gen,
    )
    assert answer.domain == "gst"
    assert answer.status == "red"
    assert answer.requires_approval is True
    assert any(c.rule_id == "GST-001" for c in answer.citations)
    assert "verified by Mahsa" in answer.provenance
    assert answer.figures  # at least one figure rendered


@pytest.mark.asyncio
async def test_answer_query_degraded_without_llm_or_mahsa(session: Session) -> None:
    # No generator, Mahsa raises -> deterministic facts only, flagged offline.
    from app.core.mahsa_client import MahsaError

    class _DownMahsa:
        async def fold(self, *a, **k):  # type: ignore[no-untyped-def]
            raise MahsaError("down")

    answer = await answer_query(
        session, query="what's our runway?", registry=build_registry(),
        settings=_SETTINGS, mahsa=_DownMahsa(),  # type: ignore[arg-type]
    )
    assert answer.domain == "treasury"
    assert answer.mahsa_up is False
    assert answer.status is None
    assert all(f.verified for f in answer.figures)  # deterministic facts are verified
    assert "deterministic figures" in answer.provenance


@pytest.mark.asyncio
async def test_answer_query_unroutable_abstains(session: Session) -> None:
    answer = await answer_query(
        session, query="hello there", registry=build_registry(), settings=_SETTINGS,
        mahsa=_FakeMahsa([]),
    )
    assert answer.domain is None
    assert answer.abstained is True
    assert answer.figures == []
