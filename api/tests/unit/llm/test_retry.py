"""P0-③ — the verify + bounded-retry loop. The evaluator is the deterministic fact set: a
number not present in the facts is 'unbacked' and must trigger regeneration; on exhaustion a
fact-built fallback is returned and flagged for approval."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.mahsa_client import FoldResult, ResponseShape, TriggeredRule, Validation
from app.llm.retry import (
    DraftResult,
    allowed_values,
    fallback_claim,
    generate_verified,
    unbacked_numbers,
)
from app.llm.schema import ActionClaim
from app.llm.tools import enrich

_SNAPSHOT = {"cash": 120000000, "monthly_burn": 30000000, "monthly_revenue": 10000000}


def _fold(
    *, requires_approval: bool = False, triggered: list[TriggeredRule] | None = None
) -> FoldResult:
    status = "red" if triggered else "green"
    return FoldResult(
        global_intent=[0.0],
        global_dims=["x"],
        validation=Validation(status=status, triggered=triggered or []),
        shape=ResponseShape(
            status=status,
            color=status,
            layout="default",
            requires_approval=requires_approval,
            global_score=100.0,
        ),
        rules_version="test",
    )


class _SequenceProducer:
    """Returns the next claim each call (last repeats), recording feedback it received."""

    def __init__(self, claims: list[ActionClaim]) -> None:
        self._claims = claims
        self._i = 0
        self.feedbacks: list[str | None] = []

    async def produce(
        self, *, snapshot: dict[str, Any], query: str, domain: str, case_id: str = "",
        feedback: str | None = None,
    ) -> ActionClaim:
        self.feedbacks.append(feedback)
        claim = self._claims[min(self._i, len(self._claims) - 1)]
        self._i += 1
        return claim


# --------------------------------------------------------------------------- verifier units


def test_unbacked_numbers_flags_invented_value() -> None:
    allowed = allowed_values(enrich(_SNAPSHOT))
    good = ActionClaim(domain="treasury", claims={"cash": "120000000", "runway_months": "6.0"})
    bad = ActionClaim(domain="treasury", claims={"cash": "999"})
    assert unbacked_numbers(good, allowed) == []
    assert unbacked_numbers(bad, allowed) == [("cash", "999")]


def test_fallback_claim_is_fully_backed_and_cites_triggered() -> None:
    fold = _fold(triggered=[TriggeredRule(
        id="GST-001", domain="gst", severity="block", description="late",
        statute="CGST Act 2017", section="Sec 47 / Rule 61", action="file",
    )])
    facts = enrich(_SNAPSHOT)
    fb = fallback_claim("treasury", facts, fold)
    assert unbacked_numbers(fb, allowed_values(facts)) == []  # every number is backed
    assert fb.rule_assertions[0].rule_id == "GST-001"


# --------------------------------------------------------------------------- the loop


@pytest.mark.asyncio
async def test_clean_first_draft_verifies_in_one_attempt() -> None:
    good = ActionClaim(domain="treasury", claims={"cash": "120000000", "runway_months": "6.0"})
    res = await generate_verified(
        _SequenceProducer([good]), snapshot=_SNAPSHOT, query="?", domain="treasury",
        fold=_fold(), max_retries=2,
    )
    assert isinstance(res, DraftResult)
    assert res.verified is True and res.attempts == 1 and res.requires_approval is False


@pytest.mark.asyncio
async def test_bad_then_good_retries_with_feedback() -> None:
    bad = ActionClaim(domain="treasury", claims={"cash": "999"})
    good = ActionClaim(domain="treasury", claims={"cash": "120000000"})
    prod = _SequenceProducer([bad, good])
    res = await generate_verified(
        prod, snapshot=_SNAPSHOT, query="?", domain="treasury", fold=_fold(), max_retries=2,
    )
    assert res.verified is True and res.attempts == 2
    assert prod.feedbacks[0] is None and prod.feedbacks[1] is not None  # correction fed back
    assert "999" in prod.feedbacks[1]


@pytest.mark.asyncio
async def test_exhaustion_falls_back_and_requires_approval() -> None:
    bad = ActionClaim(domain="treasury", claims={"cash": "999"})
    res = await generate_verified(
        _SequenceProducer([bad]), snapshot=_SNAPSHOT, query="?", domain="treasury",
        fold=_fold(), max_retries=2,
    )
    assert res.verified is False
    assert res.requires_approval is True
    assert res.attempts == 3  # 1 initial + 2 retries
    assert unbacked_numbers(res.claim, allowed_values(enrich(_SNAPSHOT))) == []  # fallback is clean


@pytest.mark.asyncio
async def test_red_books_propagate_requires_approval_even_when_verified() -> None:
    good = ActionClaim(domain="treasury", claims={"cash": "120000000"})
    res = await generate_verified(
        _SequenceProducer([good]), snapshot=_SNAPSHOT, query="?", domain="treasury",
        fold=_fold(requires_approval=True), max_retries=2,
    )
    assert res.verified is True
    assert res.requires_approval is True  # the books need sign-off regardless of a clean draft
