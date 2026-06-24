"""Persistence for the LLM trace (P1 observability). Separate from ``audit_store``: the audit
log is the tamper-evident financial record; the trace is debugging/repro metadata for the
drafting layer. We persist hashes, never raw prompts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.shared import LlmTrace
from app.llm.schema import ActionClaim


def input_hash(*, domain: str, query: str | None, snapshot: dict[str, Any]) -> str:
    """A reproducibility key over the deterministic inputs (domain + query + snapshot)."""
    blob = json.dumps(
        {"domain": domain, "query": query, "snapshot": snapshot}, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def claim_hash(claim: ActionClaim) -> str:
    return hashlib.sha256(claim.canonical().encode()).hexdigest()


def append(
    session: Session,
    *,
    timestamp: str,
    domain: str,
    audit_hash: str | None,
    model_label: str,
    input_sha256: str,
    claim: ActionClaim | None,
    attempts: int,
    verified: bool,
    requires_approval: bool,
    latency_ms: int = 0,
) -> LlmTrace:
    row = LlmTrace(
        timestamp=timestamp,
        domain=domain,
        audit_hash=audit_hash,
        model_label=model_label,
        input_sha256=input_sha256,
        claim_sha256=claim_hash(claim) if claim is not None else None,
        attempts=attempts,
        verified=1 if verified else 0,
        requires_approval=1 if requires_approval else 0,
        latency_ms=latency_ms,
    )
    session.add(row)
    session.flush()
    return row
