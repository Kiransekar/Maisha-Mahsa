"""Persistence for the hash-chained audit log. Keeps `audit.py` pure (no ORM) while this
module does the read-last-hash / append-sealed-entry dance against SQLite."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import GENESIS_HASH, AuditEntry, make_entry
from app.db.models.shared import AuditLog


def _last_hash(session: Session) -> str:
    row = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
    return row.this_hash if row and row.this_hash else GENESIS_HASH


def append(session: Session, payload: dict[str, Any]) -> AuditEntry:
    """Seal ``payload`` onto the chain and insert it. ``payload`` must contain the audit
    core fields (see ``AuditEntry.core_payload``)."""
    prev = _last_hash(session)
    entry = make_entry(prev, payload)
    g = entry.intent_global
    d = entry.intent_domain
    session.add(
        AuditLog(
            timestamp=entry.timestamp,
            action=entry.action,
            domain=entry.domain,
            user_id=entry.user_id,
            query=entry.query,
            intent_global=json.dumps(g) if g is not None else None,
            intent_domain=json.dumps(d) if d is not None else None,
            validation_status=entry.validation_status,
            rules_version=entry.rules_version,
            prev_hash=entry.prev_hash,
            this_hash=entry.this_hash,
        )
    )
    session.flush()
    return entry


def load_chain(session: Session) -> list[AuditEntry]:
    rows = session.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all()
    return [
        AuditEntry(
            timestamp=r.timestamp,
            action=r.action,
            domain=r.domain,
            user_id=r.user_id,
            query=r.query,
            intent_global=json.loads(r.intent_global) if r.intent_global else None,
            intent_domain=json.loads(r.intent_domain) if r.intent_domain else None,
            validation_status=r.validation_status or "",
            rules_version=r.rules_version,
            prev_hash=r.prev_hash or GENESIS_HASH,
            this_hash=r.this_hash or "",
        )
        for r in rows
    ]
