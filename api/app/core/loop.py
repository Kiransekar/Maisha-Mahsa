"""The Maisha-Mahsa loop (PRD §10): build a domain snapshot → fold/validate/unfold via
Mahsa → seal the result into the hash-chained audit log → return for rendering.

This is the single choke point that guarantees the Golden Rule: every result a user sees
has been recomputed and validated by Mahsa and recorded in the audit chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.domain import BaseDomainService
from app.core.mahsa_client import FoldResult, MahsaClient


@dataclass
class LoopOutcome:
    snapshot: dict[str, Any]
    fold: FoldResult
    audit_hash: str


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
) -> LoopOutcome:
    # build_snapshot may accept an optional as_of (treasury does); fall back gracefully.
    try:
        snapshot = service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        snapshot = service.build_snapshot(session)

    fold = await mahsa.fold(snapshot, domain=service.domain, query=query)

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
    session.commit()
    return LoopOutcome(snapshot=snapshot, fold=fold, audit_hash=entry.this_hash)
