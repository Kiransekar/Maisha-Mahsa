"""Unit tests for the eval harness itself. Two duties:

1. Every authored case passes in stub mode — the cases are self-consistent and the scorers
   accept correct claims, and ``build_snapshot`` runs cleanly on each seed.
2. Each scorer has a NEGATIVE case — a deliberately wrong claim that must score 0. A scorer
   that cannot fail is a vacuous test (CLAUDE.md §2).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schema import ActionClaim, RuleAssertion
from evals.cases import ALL_CASES
from evals.harness import run_all, run_case
from evals.scorers import abstains_when_thin, citation_correct, paise_exact
from evals.types import Expectation, ScriptedProducer

# --------------------------------------------------------------------------- positive path


@pytest.mark.asyncio
async def test_all_cases_pass_in_stub_mode() -> None:
    producer = ScriptedProducer({c.id: c.stub_claim for c in ALL_CASES})
    results = await run_all(ALL_CASES, producer)
    assert results, "expected at least one eval case"
    failures = [
        (r.id, [s.detail for s in r.scores if not s.passed], r.consistent)
        for r in results
        if not r.passed
    ]
    assert not failures, f"cases failed in stub mode: {failures}"


@pytest.mark.asyncio
async def test_snapshot_runs_for_every_case() -> None:
    # run_case builds the real snapshot from the seed; if a seed/build_snapshot pairing were
    # broken this raises rather than silently passing.
    producer = ScriptedProducer({c.id: c.stub_claim for c in ALL_CASES})
    for case in ALL_CASES:
        result = await run_case(case, producer)
        assert result.id == case.id


# --------------------------------------------------------------------------- pass^k drift


class _DriftingProducer:
    """Returns a different claim on each call, so pass^k must report drift."""

    def __init__(self) -> None:
        self._n = 0

    async def produce(self, *, snapshot, query, domain, case_id):  # type: ignore[no-untyped-def]
        self._n += 1
        return ActionClaim(domain=domain, claims={"x": str(self._n)})


@pytest.mark.asyncio
async def test_pass_k_detects_drift() -> None:
    case = next(c for c in ALL_CASES if c.domain == "treasury" and not c.expect.must_abstain)
    result = await run_case(case, _DriftingProducer())
    assert result.consistent is False
    assert result.passed is False


# --------------------------------------------------------------------------- negative scorers


def test_paise_exact_fails_on_wrong_number() -> None:
    expect = Expectation(claims={"cash_paise": "120000000"})
    good = ActionClaim(domain="treasury", claims={"cash_paise": "120000000"})
    bad = ActionClaim(domain="treasury", claims={"cash_paise": "120000001"})
    missing = ActionClaim(domain="treasury", claims={})
    assert paise_exact(good, expect).passed is True
    assert paise_exact(bad, expect).passed is False
    assert paise_exact(missing, expect).passed is False


def test_citation_correct_fails_when_missing_or_malformed() -> None:
    expect = Expectation(citations=["CGST Act 2017 / Sec 47 / Rule 61"])
    good = ActionClaim(
        domain="gst",
        rule_assertions=[
            RuleAssertion(rule_id="GST-001", statute="CGST Act 2017", section="Sec 47 / Rule 61")
        ],
    )
    missing = ActionClaim(domain="gst", rule_assertions=[])
    malformed = ActionClaim(
        domain="gst",
        rule_assertions=[RuleAssertion(rule_id="GST-001", statute="CGST Act 2017", section="")],
    )
    assert citation_correct(good, expect).passed is True
    assert citation_correct(missing, expect).passed is False
    assert citation_correct(malformed, Expectation()).passed is False


def test_abstains_when_thin_both_directions() -> None:
    thin = Expectation(must_abstain=True)
    answerable = Expectation(claims={"cash_paise": "1"})
    abstained = ActionClaim(domain="treasury", abstained=True)
    answered = ActionClaim(domain="treasury", claims={"cash_paise": "1"})
    # correct behaviours
    assert abstains_when_thin(abstained, thin).passed is True
    assert abstains_when_thin(answered, answerable).passed is True
    # wrong behaviours
    assert abstains_when_thin(answered, thin).passed is False  # should have abstained
    assert abstains_when_thin(abstained, answerable).passed is False  # abstained on answerable
    # abstained but still emitted numbers
    leaky = ActionClaim(domain="treasury", abstained=True, claims={"cash_paise": "1"})
    assert abstains_when_thin(leaky, thin).passed is False


def test_action_claim_rejects_float_money() -> None:
    # StrictStr must reject a raw float in claims — no 0.1-style value can enter.
    with pytest.raises(ValidationError):
        ActionClaim(domain="treasury", claims={"cash_paise": 120000000.0})  # type: ignore[dict-item]
