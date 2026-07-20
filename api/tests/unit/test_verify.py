"""verify_figure maps a Mahsa /fold response to a figure verdict: verified / blocked (Prime
Directive mismatch) / honest-pending. The live behaviour against the real binary is covered in
tests/integration/test_verified_flow.py; here we pin the mapping with a fake Mahsa."""

import pytest

from app.core.mahsa_client import (
    FoldResult,
    RecomputeCheck,
    RecomputeClaim,
    ResponseShape,
    TriggeredRule,
    Validation,
)
from app.core.verify import MAHSA_PARITY_RULE, verify_figure

pytestmark = pytest.mark.asyncio


def _fold(check: RecomputeCheck, *, blocked: bool) -> FoldResult:
    triggered = []
    if blocked:
        triggered = [
            TriggeredRule(
                id=MAHSA_PARITY_RULE,
                domain="global",
                severity="Block",
                description="mismatch",
                statute="Mahsa Prime Directive",
                section="MMX-1.0 §0.4",
                action="block",
            )
        ]
    return FoldResult(
        global_intent=[0.0] * 8,
        global_dims=["x"] * 8,
        validation=Validation(status="red" if blocked else "green", triggered=triggered),
        shape=ResponseShape(
            status="red" if blocked else "green",
            color="red" if blocked else "green",
            layout="global",
            requires_approval=blocked,
            global_score=0.0,
        ),
        rules_version="test",
        recompute=[check],
    )


class _FakeMahsa:
    def __init__(self, fold: FoldResult) -> None:
        self._fold = fold

    async def fold(self, snapshot, *, recompute_claims=None, **kw):
        return self._fold


_CLAIM = RecomputeClaim(target="interest_234c", inputs={"x": 1}, claimed_paise=100)


async def test_verified_when_recomputed_and_matches():
    check = RecomputeCheck(
        target="interest_234c", claimed_paise=100, recomputed_paise=100, matches=True, note="ok"
    )
    v = await verify_figure(_FakeMahsa(_fold(check, blocked=False)), _CLAIM)
    assert v.verified and not v.blocked and not v.honest_pending


async def test_blocked_on_recomputable_mismatch():
    check = RecomputeCheck(
        target="interest_234c",
        claimed_paise=100,
        recomputed_paise=200,
        matches=False,
        note="MISMATCH",
    )
    v = await verify_figure(_FakeMahsa(_fold(check, blocked=True)), _CLAIM)
    assert v.blocked and not v.verified


async def test_honest_pending_when_not_recomputable():
    check = RecomputeCheck(
        target="unknown", claimed_paise=100, recomputed_paise=None, matches=False, note="pending"
    )
    v = await verify_figure(_FakeMahsa(_fold(check, blocked=False)), _CLAIM)
    assert v.honest_pending and not v.verified and not v.blocked
