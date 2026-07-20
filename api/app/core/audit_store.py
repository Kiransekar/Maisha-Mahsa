"""Persistence for the hash-chained audit log. Keeps `audit.py` pure (no ORM) while this
module does the read-last-hash / append-sealed-entry dance against SQLite."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import (
    GENESIS_HASH,
    AnchorRecord,
    AuditEntry,
    compute_daily_root,
    make_entry,
    tenant_genesis,
    verify_chain,
)
from app.db.models.shared import AuditLog


def _last_hash(session: Session) -> str:
    row = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
    return row.this_hash if row and row.this_hash else GENESIS_HASH


def _to_entry(r: AuditLog) -> AuditEntry:
    return AuditEntry(
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


def _by_prev(session: Session) -> dict[str, AuditLog]:
    """Index every row by its ``prev_hash``. Keys are globally unique: a genesis (distinct per
    tenant) or a predecessor's ``this_hash`` (a distinct sha256), so no two rows collide even
    with many tenants' chains interleaved in the one table."""
    rows = session.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all()
    return {(r.prev_hash or GENESIS_HASH): r for r in rows}


def _walk(by_prev: dict[str, AuditLog], start: str) -> list[AuditLog]:
    """Follow the hash links from ``start`` (a genesis) to the chain head."""
    chain: list[AuditLog] = []
    prev = start
    while prev in by_prev:
        r = by_prev[prev]
        chain.append(r)
        prev = r.this_hash or ""
    return chain


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
    return [_to_entry(r) for r in rows]


# --- WS4.4 per-tenant chain ---------------------------------------------------------------
# Each org has an independent chain rooted at ``tenant_genesis(org)``. Entries persist into the
# same table, but a tenant's chain is reconstructed by following its hash links from its own
# genesis — so one tenant's entries never interleave with another's, without needing an org
# column here (that persistence detail lands with the WS4.1/WS4.2 schema/migration work).
# ponytail: O(n) index rebuild per call; fine at SQLite scale, revisit if audit volume explodes.


def _tenant_head(session: Session, org: str) -> str:
    """Head hash of ``org``'s chain (its genesis if the tenant has no entries yet)."""
    genesis = tenant_genesis(org)
    chain = _walk(_by_prev(session), genesis)
    return (chain[-1].this_hash or "") if chain else genesis


def append_for(session: Session, org: str, payload: dict[str, Any]) -> AuditEntry:
    """Seal ``payload`` onto ``org``'s independent chain and insert it (WS4.4). Same fields as
    :func:`append`; the entry chains onto this tenant's head (or its genesis for the first
    entry), so it can never link into another tenant's chain."""
    prev = _tenant_head(session, org)
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


def load_chain_for(session: Session, org: str) -> list[AuditEntry]:
    """Reconstruct just ``org``'s chain, in seal order, from its genesis."""
    return [_to_entry(r) for r in _walk(_by_prev(session), tenant_genesis(org))]


def verify_chain_for(session: Session, org: str) -> bool:
    """Validate exactly ``org``'s chain (the ``/audit/verify`` per-tenant capability, WS4.4).
    Ignores every other tenant's entries; tamper in another tenant cannot affect this result."""
    return verify_chain(load_chain_for(session, org), genesis=tenant_genesis(org))


def compute_daily_root_for(session: Session, org: str, day: str) -> AnchorRecord:
    """Anchorable daily root over ``org``'s entries whose ``timestamp`` falls on ``day``
    (``YYYY-MM-DD`` prefix). The returned root is handed to ops for external timestamping."""
    day_entries = [e for e in load_chain_for(session, org) if e.timestamp.startswith(day)]
    return compute_daily_root(org, day, day_entries)
