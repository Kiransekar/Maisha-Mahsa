"""Persistence for human approve/reject decisions (F4). A decision is keyed by
``(domain, state_hash)`` — the latest one wins, so re-approving after the books change is
natural."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.shared import Decision


def append(
    session: Session,
    *,
    timestamp: str,
    domain: str,
    decision: str,
    state_hash: str,
    audit_hash: str | None,
    user_id: str,
    item_id: str | None = None,
) -> Decision:
    row = Decision(
        timestamp=timestamp,
        domain=domain,
        decision=decision,
        state_hash=state_hash,
        audit_hash=audit_hash,
        user_id=user_id,
        item_id=item_id,
    )
    session.add(row)
    session.flush()
    return row


def resolution(session: Session, domain: str, state_hash: str) -> str | None:
    """The latest decision for this exact domain+state, or None if still pending."""
    row = session.scalars(
        select(Decision)
        .where(Decision.domain == domain, Decision.state_hash == state_hash)
        .order_by(Decision.id.desc())
        .limit(1)
    ).first()
    return row.decision if row else None
