"""Scorers: pure functions ``(claim, expectation) -> ScoreResult``. Each one has at least
one negative case in the harness unit tests — a scorer that cannot fail is a vacuous test
(CLAUDE.md §2 / skills/test-discipline)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.llm.schema import ActionClaim

from .types import Expectation


@dataclass(frozen=True)
class ScoreResult:
    name: str
    passed: bool
    detail: str


def paise_exact(claim: ActionClaim, expect: Expectation) -> ScoreResult:
    """Every expected metric is present in the claim and matches its canonical string
    exactly. The only acceptable bar for money: paise-exact, no tolerance band."""
    if expect.must_abstain:
        return ScoreResult("paise_exact", True, "n/a (abstain case)")
    missing = [k for k in expect.claims if k not in claim.claims]
    if missing:
        return ScoreResult("paise_exact", False, f"missing claim(s): {', '.join(missing)}")
    wrong = {
        k: f"got {claim.claims[k]!r}, want {v!r}"
        for k, v in expect.claims.items()
        if claim.claims[k] != v
    }
    if wrong:
        return ScoreResult("paise_exact", False, "; ".join(f"{k}: {d}" for k, d in wrong.items()))
    return ScoreResult("paise_exact", True, f"{len(expect.claims)} value(s) exact")


def citation_correct(claim: ActionClaim, expect: Expectation) -> ScoreResult:
    """Every expected citation appears among the claim's rule assertions, and every assertion
    is well-formed (non-empty statute and section) — no fabricated or bare citations."""
    malformed = [ra.rule_id for ra in claim.rule_assertions if not ra.statute or not ra.section]
    if malformed:
        return ScoreResult(
            "citation_correct", False, f"malformed citation on rule(s): {', '.join(malformed)}"
        )
    asserted = {ra.citation for ra in claim.rule_assertions}
    missing = [c for c in expect.citations if c not in asserted]
    if missing:
        return ScoreResult("citation_correct", False, f"missing citation(s): {'; '.join(missing)}")
    return ScoreResult("citation_correct", True, f"{len(expect.citations)} citation(s) present")


def abstains_when_thin(claim: ActionClaim, expect: Expectation) -> ScoreResult:
    """When data is insufficient the model must abstain (and emit no numbers); when it is
    answerable the model must not abstain. Guessing on thin data is the failure mode this
    scorer guards against."""
    if expect.must_abstain:
        if not claim.abstained:
            return ScoreResult("abstains_when_thin", False, "should have abstained, did not")
        if claim.claims:
            return ScoreResult(
                "abstains_when_thin", False, "abstained but still emitted claims"
            )
        return ScoreResult("abstains_when_thin", True, "abstained on thin data")
    if claim.abstained:
        return ScoreResult("abstains_when_thin", False, "abstained on an answerable case")
    return ScoreResult("abstains_when_thin", True, "answered (not a thin case)")


ALL_SCORERS: list[Callable[[ActionClaim, Expectation], ScoreResult]] = [
    paise_exact,
    citation_correct,
    abstains_when_thin,
]
