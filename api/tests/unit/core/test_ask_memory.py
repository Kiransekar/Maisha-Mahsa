"""SPEC-MEMCITE-1.0 MEM.P0-4 — Ask Maisha threading: ``answer_query`` takes the verified
Principal, injects the org profile block as context, and runs org-scoped lexical recall over
the org's OWN sealed audit chain, rendered as decision+hash citations.

Pinned here, mutation-proof:
  * two-org isolation — recall as org A can never return an org B decision (the entries come
    from A's hash chain reconstructed from A's tenant genesis; B's entries cannot link in);
  * recall citations carry the decision AND the sealed audit hash, never a number-as-truth;
  * LLM-off determinism — with no generator the whole Answer (figures + recall citations) is
    byte-identical across calls, so recall keeps working with the LLM off (spec §A1 deferral
    condition made a test);
  * the profile/CFO block reaches the generator as `memory` context, labeled context-only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core import audit_store, memory
from app.core.ask import answer_query
from app.core.mahsa_client import MahsaError
from app.core.principal import Principal
from app.core.rbac import Role
from app.domains import build_registry
from app.llm.schema import ActionClaim

ORG_A = Principal(user_id="user-a", org_id="org-a", role=Role.OWNER, email="a@example.com")
ORG_B = Principal(user_id="user-b", org_id="org-b", role=Role.OWNER, email="b@example.com")

_SETTINGS = SimpleNamespace(
    mahsa_url="http://unused",
    llm_provider="off",
    llm_max_retries=2,
    ollama_model="m",
    claude_model="c",
)


class _DownMahsa:
    async def fold(self, *a: Any, **k: Any) -> Any:
        raise MahsaError("down")


def _seal_decision(session: Session, org: str, query: str, action: str = "treasury.fold") -> str:
    entry = audit_store.append_for(
        session,
        org,
        {
            "timestamp": "2026-07-23T10:00:00+00:00",
            "action": action,
            "domain": "treasury",
            "user_id": "founder",
            "query": query,
            "intent_global": None,
            "intent_domain": None,
            "validation_status": "green",
            "rules_version": "test",
        },
    )
    return entry.this_hash


# ---- recall: org isolation ---------------------------------------------------------------


def test_recall_returns_only_own_org_rows_in_a_two_org_fixture(session: Session) -> None:
    a_hash = _seal_decision(session, ORG_A.org_id, "runway check for org a")
    b_hash = _seal_decision(session, ORG_B.org_id, "runway check for org b")
    assert a_hash != b_hash

    recalled = memory.recall_decisions(session, ORG_A, "what's our runway?")
    assert recalled, "org A's own sealed decision must be recalled"
    hashes = {r["audit_hash"] for r in recalled}
    assert a_hash in hashes
    assert b_hash not in hashes  # the isolation assertion: B's chain can never leak into A's

    # And symmetrically for B — neither org sees the other's decisions.
    hashes_b = {r["audit_hash"] for r in memory.recall_decisions(session, ORG_B, "runway?")}
    assert b_hash in hashes_b
    assert a_hash not in hashes_b


def test_recall_is_lexical_and_returns_decision_plus_hash_never_figures(
    session: Session,
) -> None:
    matched = _seal_decision(session, ORG_A.org_id, "gstr-3b filing decision", "gst.fold")
    _seal_decision(session, ORG_A.org_id, "payroll run for june", "payroll.fold")

    recalled = memory.recall_decisions(session, ORG_A, "gstr-3b filing status?")
    assert [r["audit_hash"] for r in recalled] == [matched]  # unrelated decision not recalled
    r = recalled[0]
    assert r["action"] == "gst.fold"
    assert r["audit_hash"] == matched
    assert "gst.fold" in r["decision"]  # decision text names the sealed event, not a number
    assert set(r) == {"action", "domain", "timestamp", "decision", "audit_hash"}


# ---- answer_query threading --------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_query_with_principal_adds_recall_citations_with_audit_hash(
    session: Session,
) -> None:
    a_hash = _seal_decision(session, ORG_A.org_id, "runway check for org a")
    _seal_decision(session, ORG_B.org_id, "runway check for org b")

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
        principal=ORG_A,
    )
    assert answer.domain == "treasury"
    recall = [c for c in answer.citations if c.audit_hash is not None]
    assert [c.audit_hash for c in recall] == [a_hash]  # own org only, hash carried through
    assert recall[0].rule_id == "decision:treasury.fold"
    assert recall[0].citation == f"audit {a_hash[:12]}"
    assert recall[0].text.startswith("treasury.fold")


@pytest.mark.asyncio
async def test_answer_query_llm_off_is_deterministic_with_recall(session: Session) -> None:
    _seal_decision(session, ORG_A.org_id, "runway check for org a")
    registry = build_registry()

    async def ask() -> Any:
        return await answer_query(
            session,
            query="what's our runway?",
            registry=registry,
            settings=_SETTINGS,
            mahsa=_DownMahsa(),  # type: ignore[arg-type]
            principal=ORG_A,
        )

    first, second = await ask(), await ask()
    assert first == second  # whole Answer: figures, citations, narrative, provenance
    assert first.figures, "deterministic figures still ship with the LLM off"
    assert any(c.audit_hash for c in first.citations), "recall works with the LLM off"


@pytest.mark.asyncio
async def test_answer_query_without_principal_is_unchanged(session: Session) -> None:
    _seal_decision(session, ORG_A.org_id, "runway check for org a")
    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
    )
    # No verified caller -> no memory, no recall: the pre-MEMCITE behaviour, fail closed.
    assert answer.citations == []


# ---- the no-fold path (Mahsa down + LLM on) — MED-1 -------------------------------------

#: A figure that exists ONLY in the org's memory — deliberately absent from every snapshot fact.
_SMUGGLED = "424242424"


@pytest.mark.asyncio
async def test_no_fold_path_memory_only_number_never_ships_and_is_flagged(
    session: Session,
) -> None:
    """MED-1 root fix: with Mahsa DOWN and the LLM on, the draft still runs through
    ``retry.generate_verified`` — a number seeded only in memory fails the number firewall,
    the fact-built fallback ships instead, and the answer is flagged requires_approval. If
    the no-fold path ever bypasses the firewall again, the echoing draft ships verbatim and
    every assertion below fails."""
    memory.set_cfo(
        session,
        ORG_A,
        f"- Board pre-approved ₹{_SMUGGLED} for the new office",
        now="2026-07-23T12:00:00",
    )

    class _EchoGen:
        label = "test:model"
        memories: list[str | None] = []

        async def produce(
            self,
            *,
            snapshot: dict[str, Any],
            query: str,
            domain: str,
            case_id: str = "",
            feedback: str | None = None,
            memory: str | None = None,
        ) -> ActionClaim:
            _EchoGen.memories.append(memory)
            return ActionClaim(
                domain=domain,
                narrative=f"The board approved ₹{_SMUGGLED}.",
                claims={"office_spend": _SMUGGLED},
            )

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
        generator=_EchoGen(),
        principal=ORG_A,
    )
    assert answer.mahsa_up is False  # this really is the no-fold path
    # The memory (with the smuggled number) really reached the generator — not vacuous.
    assert _EchoGen.memories and _EchoGen.memories[0] is not None
    assert _SMUGGLED in _EchoGen.memories[0]
    # The firewall held: the memory-only number is NOWHERE — not narrative, not a figure.
    assert _SMUGGLED not in answer.narrative
    assert all(_SMUGGLED not in f.value for f in answer.figures)
    # And the unverifiable draft never reaches a human unflagged (§0.4).
    assert answer.requires_approval is True
    assert "pending review" in answer.provenance
    assert "verified by Mahsa" not in answer.provenance


@pytest.mark.asyncio
async def test_no_fold_path_clean_draft_is_still_flagged_fail_closed(session: Session) -> None:
    """Even a draft whose every number is fact-backed is flagged on the no-fold path: Mahsa
    never saw the books, so nothing it would gatekeep may pass unflagged (§0.4 fail closed)."""

    class _CleanGen:
        label = "test:model"

        async def produce(
            self,
            *,
            snapshot: dict[str, Any],
            query: str,
            domain: str,
            case_id: str = "",
            feedback: str | None = None,
            memory: str | None = None,
        ) -> ActionClaim:
            return ActionClaim(domain=domain, narrative="All quiet.", claims={})

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
        generator=_CleanGen(),
        principal=ORG_A,
    )
    assert answer.mahsa_up is False
    assert answer.narrative == "All quiet."  # the clean draft itself still ships
    assert answer.requires_approval is True  # ...but never unflagged with the gate down
    assert "verified by Mahsa" not in answer.provenance
    assert "pending review" in answer.provenance


@pytest.mark.asyncio
async def test_profile_block_reaches_generator_as_labeled_memory_context(
    session: Session,
) -> None:
    memory.set_cfo(session, ORG_A, "- Prefer the old tax regime", now="2026-07-23T12:00:00")

    class _CaptureGen:
        label = "test:model"
        memories: list[str | None] = []

        async def produce(
            self,
            *,
            snapshot: dict[str, Any],
            query: str,
            domain: str,
            case_id: str = "",
            feedback: str | None = None,
            memory: str | None = None,
        ) -> ActionClaim:
            _CaptureGen.memories.append(memory)
            return ActionClaim(domain=domain, narrative="ok", claims={})

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
        generator=_CaptureGen(),
        principal=ORG_A,
    )
    assert answer.domain == "treasury"
    assert _CaptureGen.memories and _CaptureGen.memories[0] is not None
    assert "Prefer the old tax regime" in _CaptureGen.memories[0]
    assert memory.CONTEXT_ONLY_LABEL in _CaptureGen.memories[0]
