"""Core types for the eval harness: a declarative :class:`EvalCase`, its
:class:`Expectation` (hand-authored ground truth), and the :class:`ClaimProducer` protocol
the runner drives (a stub today, the real LLM in P0-②)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.llm.maisha import ClaimProducer
from app.llm.schema import ActionClaim

__all__ = ["ClaimProducer", "EvalCase", "Expectation", "ScriptedProducer"]


@dataclass(frozen=True)
class Expectation:
    """Ground truth for a case, authored by hand and cross-checked against Mahsa.

    ``claims`` are exact canonical strings (paise for money). ``citations`` are
    ``"<statute> / <section>"`` strings that must appear among the claim's rule assertions.
    ``expected_status`` is the Mahsa verdict the snapshot should produce — checked by the
    integration path (real Mahsa binary), not the pure scorers.
    """

    claims: dict[str, str] = field(default_factory=dict)
    citations: list[str] = field(default_factory=list)
    must_abstain: bool = False
    expected_status: str | None = None  # green / yellow / red


@dataclass(frozen=True)
class EvalCase:
    """One scenario: seed a fresh DB, ask ``query`` of ``domain``, expect ``expect``.

    ``stub_claim`` is the pre-authored claim the :class:`ScriptedProducer` returns in
    no-LLM (P0-①) mode — it must itself satisfy ``expect`` (a case that can't pass with its
    own ground-truth claim is a broken case).
    """

    id: str
    domain: str
    query: str
    seed: Callable[[Session], None]
    expect: Expectation
    stub_claim: ActionClaim
    as_of: date | None = None
    k: int = 3  # pass^k runs


class ScriptedProducer:
    """Stub producer for P0-①: returns each case's pre-authored ``stub_claim`` verbatim.
    Lets ``make eval`` and the harness unit tests run in CI with no model. Deterministic by
    construction, so every case is trivially pass^k-consistent — the real consistency signal
    arrives with the LLM producer in P0-②."""

    def __init__(self, claims_by_case: dict[str, ActionClaim]) -> None:
        self._by_case = dict(claims_by_case)

    async def produce(
        self,
        *,
        snapshot: dict[str, Any],
        query: str,
        domain: str,
        case_id: str = "",
        feedback: str | None = None,
        memory: str | None = None,  # accepted for ClaimProducer conformance; scripted = ignored
    ) -> ActionClaim:
        if case_id not in self._by_case:
            raise KeyError(f"no scripted claim for case '{case_id}'")
        return self._by_case[case_id]
