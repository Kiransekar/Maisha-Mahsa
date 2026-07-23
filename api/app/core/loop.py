"""The Maisha-Mahsa loop (PRD §10): build a domain snapshot → fold/validate/unfold via
Mahsa → seal the result into the hash-chained audit log → return for rendering.

This is the single choke point that guarantees the Golden Rule: every result a user sees
has been recomputed and validated by Mahsa and recorded in the audit chain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core import audit_store, trace_store
from app.core import memory as org_memory
from app.core.domain import BaseDomainService
from app.core.mahsa_client import FoldResult, MahsaClient
from app.core.principal import current_org
from app.llm.maisha import ClaimProducer
from app.llm.retry import generate_verified
from app.llm.schema import ActionClaim


@dataclass
class LoopOutcome:
    snapshot: dict[str, Any]
    fold: FoldResult
    audit_hash: str
    claim: ActionClaim | None = None
    claim_verified: bool | None = None  # None when no LLM ran
    requires_approval: bool = False


async def run_loop(
    *,
    session: Session,
    mahsa: MahsaClient,
    service: BaseDomainService,
    timestamp: str,
    as_of: date | None = None,
    query: str | None = None,
    action: str = "fold",
    user_id: str = "founder",
    generator: ClaimProducer | None = None,
    max_retries: int = 2,
    memory: str | None = None,
) -> LoopOutcome:
    # build_snapshot may accept an optional as_of (treasury does); fall back gracefully.
    try:
        snapshot = service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        snapshot = service.build_snapshot(session)

    # Prime-Directive claims (§0.4): the domain's recomputable figures, for Mahsa to
    # independently recompute and BLOCK on mismatch. Same optional-as_of fallback.
    try:
        claims = service.recompute_claims(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        claims = service.recompute_claims(session)

    # Mahsa folds/validates the deterministic snapshot first — its verdict is the source of
    # truth and is independent of any LLM draft (the Golden Rule).
    fold = await mahsa.fold(
        snapshot, domain=service.domain, query=query, recompute_claims=claims or None
    )

    # Optional drafting step with verification: the LLM proposes an ActionClaim, every number
    # is checked against the deterministic facts, and unbacked numbers trigger bounded
    # regeneration; on exhaustion a fact-built fallback is used and flagged for approval. The
    # claim never overrides Mahsa. With no generator the loop is deterministic as before.
    claim: ActionClaim | None = None
    claim_verified: bool | None = None
    attempts = 0
    latency_ms = 0
    requires_approval = fold.shape.requires_approval
    if generator is not None and query:
        # SPEC-MEMCITE-1.0 §A7: the ONE choke point where org memory reaches the drafting
        # layer. The org comes from the request contextvar the auth middleware set from the
        # verified JWT (never a parameter a caller could spoof); no authenticated org means no
        # memory. Memory is CONTEXT threaded to the prompt — generate_verified's facts map is
        # built from the snapshot alone, so a memory figure can never verify (§A4).
        if memory is None and (org := current_org()):
            memory = org_memory.profile_block(session, org) or None
        started = time.perf_counter()
        draft = await generate_verified(
            generator,
            snapshot=snapshot,
            query=query,
            domain=service.domain,
            fold=fold,
            max_retries=max_retries,
            memory=memory,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        claim = draft.claim
        claim_verified = draft.verified
        attempts = draft.attempts
        requires_approval = requires_approval or draft.requires_approval

    entry = audit_store.append(
        session,
        {
            "timestamp": timestamp,
            "action": action,
            "domain": service.domain,
            "user_id": user_id,
            "query": query,
            "intent_global": fold.global_intent,
            "intent_domain": fold.domain_intent,
            "validation_status": fold.validation.status,
            "rules_version": fold.rules_version,
        },
    )

    # LLM trace (observability; hashes only, no raw prompt) — only when a draft was produced.
    if claim is not None:
        trace_store.append(
            session,
            timestamp=timestamp,
            domain=service.domain,
            audit_hash=entry.this_hash,
            model_label=getattr(generator, "label", "unknown"),
            input_sha256=trace_store.input_hash(
                domain=service.domain, query=query, snapshot=snapshot
            ),
            claim=claim,
            attempts=attempts,
            verified=bool(claim_verified),
            requires_approval=requires_approval,
            latency_ms=latency_ms,
        )

    session.commit()
    return LoopOutcome(
        snapshot=snapshot,
        fold=fold,
        audit_hash=entry.this_hash,
        claim=claim,
        claim_verified=claim_verified,
        requires_approval=requires_approval,
    )
