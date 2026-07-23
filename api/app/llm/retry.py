"""The evaluator-optimizer loop (P0-③). The *evaluator* is the deterministic fact set: every
number a claim states must be a value the audited engines actually produced (the Golden Rule
applied to the draft, live). The *optimizer* is bounded regeneration: on an unbacked number we
feed the discrepancy back to the model and ask again. On exhaustion we fall back to a claim
built directly from the facts and flag it for human approval — never ship an unverified number.

Mahsa's verdict (``fold``) describes the *books*, not the draft, so it is not a retry trigger;
its triggered rules are passed into the feedback so the regenerated narrative cites what the
authoritative rule engine flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.mahsa_client import FoldResult
from app.llm import tools
from app.llm.maisha import ClaimProducer
from app.llm.schema import ActionClaim, RuleAssertion


@dataclass
class DraftResult:
    claim: ActionClaim
    attempts: int
    verified: bool  # every stated number is backed by a deterministic fact (or a clean abstain)
    requires_approval: bool  # Mahsa flagged the books, or the draft fell back after exhaustion


def _canon(value: Any) -> str:
    return str(value)


def allowed_values(facts: dict[str, Any]) -> set[str]:
    return {_canon(v) for v in facts.values()}


def unbacked_numbers(claim: ActionClaim, allowed: set[str]) -> list[tuple[str, str]]:
    """Claim entries whose value is not any deterministic fact value — i.e. invented numbers."""
    return [(k, v) for k, v in claim.claims.items() if v not in allowed]


def _triggered_assertions(fold: FoldResult | None) -> list[RuleAssertion]:
    if fold is None:  # Mahsa down: no rules were evaluated, so none are asserted
        return []
    return [
        RuleAssertion(rule_id=t.id, statute=t.statute, section=t.section)
        for t in fold.validation.triggered
    ]


def fallback_claim(domain: str, facts: dict[str, Any], fold: FoldResult | None) -> ActionClaim:
    """A fully-backed claim assembled directly from the facts + Mahsa's triggered rules. Used
    when the model can't produce a verified draft within the retry budget."""
    claims = {k: _canon(v) for k, v in facts.items() if isinstance(v, (int, float))}
    return ActionClaim(
        domain=domain,
        narrative=(
            "Auto-generated from verified figures; the drafted answer failed number "
            "verification and is pending review."
        ),
        claims=claims,
        rule_assertions=_triggered_assertions(fold),
    )


def _feedback(bad: list[tuple[str, str]], facts: dict[str, Any], fold: FoldResult | None) -> str:
    bad_str = "; ".join(f"{k}={v}" for k, v in bad)
    triggered = (", ".join(t.id for t in fold.validation.triggered) if fold else "") or "none"
    return (
        f"These reported numbers are not in the FACTS block and must not be used: {bad_str}. "
        f"State only values present in FACTS. Mahsa triggered these rules: {triggered}."
    )


async def generate_verified(
    generator: ClaimProducer,
    *,
    snapshot: dict[str, Any],
    query: str,
    domain: str,
    fold: FoldResult | None,
    max_retries: int,
    memory: str | None = None,
) -> DraftResult:
    # §A4 firewall: `facts` (and therefore `allowed`) comes ONLY from tools.enrich(snapshot).
    # `memory` is context threaded to the generator's prompt and is NEVER merged here — so a
    # number that exists only in memory can never become an allowed value and never verifies.
    facts = tools.enrich(snapshot)
    allowed = allowed_values(facts)
    feedback: str | None = None
    # Only pass memory when present, so ClaimProducer stubs predating the kwarg keep working.
    extra: dict[str, str] = {"memory": memory} if memory else {}

    for attempt in range(1, max_retries + 2):  # 1 initial try + max_retries
        claim = await generator.produce(
            snapshot=snapshot, query=query, domain=domain, feedback=feedback, **extra
        )
        bad = unbacked_numbers(claim, allowed)
        if not bad:
            # With Mahsa down (fold is None) the numbers are fact-checked here but the
            # gatekeeper never saw the books — fail closed: the draft needs a human (§0.4).
            return DraftResult(
                claim=claim,
                attempts=attempt,
                verified=True,
                requires_approval=fold.shape.requires_approval if fold is not None else True,
            )
        feedback = _feedback(bad, facts, fold)

    return DraftResult(
        claim=fallback_claim(domain, facts, fold),
        attempts=max_retries + 1,
        verified=False,
        requires_approval=True,
    )
