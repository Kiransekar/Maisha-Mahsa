"""The hash-chained, append-only audit log (PRD §11.2).

Each entry's hash covers the canonical JSON of its fields **plus the previous hash**, so
tampering with any historical record breaks every subsequent hash. Verification is O(n)
and needs no secrets.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_json(payload: dict[str, Any] | list[Any]) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace, UTF-8. Accepts a list
    too — SPEC-MEMCITE-1.0 row hashes are ``sha256(canonical_json([cells...]))``."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def tenant_genesis(org: str) -> str:
    """Per-tenant chain root (WS4.4). Each org's chain starts from its OWN genesis instead of
    the shared ``GENESIS_HASH``, so an entry from org A can never be replayed into org B — the
    org id is bound cryptographically into the first link. Reuses the existing hash primitive;
    not a secret. An empty ``org`` is rejected (a tenant must be identified)."""
    if not org:
        raise ValueError("org must be non-empty")
    h = hashlib.sha256()
    h.update(b"maisha-audit-genesis:")
    h.update(org.encode("utf-8"))
    return h.hexdigest()


def compute_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    """``this_hash = sha256(prev_hash || canonical_json(entry))``."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(canonical_json(entry).encode("utf-8"))
    return h.hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    action: str
    domain: str
    user_id: str
    query: str | None
    intent_global: list[float] | None
    intent_domain: list[float] | None
    validation_status: str
    rules_version: str
    prev_hash: str
    this_hash: str

    def core_payload(self) -> dict[str, Any]:
        """The fields covered by the hash (everything except the hashes themselves)."""
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "domain": self.domain,
            "user_id": self.user_id,
            "query": self.query,
            "intent_global": self.intent_global,
            "intent_domain": self.intent_domain,
            "validation_status": self.validation_status,
            "rules_version": self.rules_version,
        }


def make_entry(prev_hash: str, payload: dict[str, Any]) -> AuditEntry:
    """Build a sealed entry chained onto ``prev_hash``."""
    this_hash = compute_hash(prev_hash, payload)
    return AuditEntry(
        timestamp=payload["timestamp"],
        action=payload["action"],
        domain=payload["domain"],
        user_id=payload["user_id"],
        query=payload.get("query"),
        intent_global=payload.get("intent_global"),
        intent_domain=payload.get("intent_domain"),
        validation_status=payload["validation_status"],
        rules_version=payload["rules_version"],
        prev_hash=prev_hash,
        this_hash=this_hash,
    )


def verify_chain(entries: list[AuditEntry], genesis: str = GENESIS_HASH) -> bool:
    """True iff the chain is intact: each entry links to the previous and its hash matches
    a fresh recomputation. An empty chain is trivially valid.

    ``genesis`` is the value the first entry must chain onto — ``GENESIS_HASH`` for the legacy
    global chain, or :func:`tenant_genesis` ``(org)`` to verify exactly one tenant's chain
    (WS4.4). Entries from a different tenant chain onto a different genesis, so passing org A's
    genesis validates A's entries and ignores B's."""
    prev = genesis
    for e in entries:
        if e.prev_hash != prev:
            return False
        if compute_hash(prev, e.core_payload()) != e.this_hash:
            return False
        prev = e.this_hash
    return True


def edit_log_payload(
    *,
    timestamp: str,
    domain: str,
    user_id: str,
    record_type: str,
    record_id: str,
    operation: str,
    rules_version: str,
    before_hash: str | None = None,
    after_hash: str | None = None,
) -> dict[str, Any]:
    """Build the audit payload for a single accounting-record write (WS4.4 edit-log
    formalization → MCA audit-trail conformance).

    Every create/update/delete of a books-of-account record MUST append one of these onto the
    tenant chain (non-disablable — wiring into each write is WS4.2). The *content* of the record
    never enters the log; only opaque keys (``record_type``/``record_id``) and ``before``/
    ``after`` content **hashes** do, so the entry proves *what changed* while carrying no PII
    (§0.8). Because ``query`` is inside the hashed ``core_payload``, the change descriptor is
    itself tamper-evident. Returns a dict ready for :func:`app.core.audit_store.append_for`."""
    if operation not in ("create", "update", "delete"):
        raise ValueError(f"operation must be create/update/delete, got {operation!r}")
    descriptor = canonical_json(
        {
            "op": operation,
            "type": record_type,
            "id": record_id,
            "before": before_hash,
            "after": after_hash,
        }
    )
    return {
        "timestamp": timestamp,
        "action": f"record.{operation}",
        "domain": domain,
        "user_id": user_id,
        "query": descriptor,
        "intent_global": None,
        "intent_domain": None,
        "validation_status": "recorded",
        "rules_version": rules_version,
    }


@dataclass(frozen=True)
class AnchorRecord:
    """A day's chain-root for external timestamp anchoring (WS4.4).

    ``root`` deterministically commits to every entry the tenant sealed on ``day`` (change any
    entry → its ``this_hash`` changes → ``root`` changes). ``external_ref`` is filled in by ops
    AFTER the root is timestamped by an independent authority (RFC-3161 TSA, or a public-chain
    anchor); the external submission is an ops/Human integration, not done here."""

    org: str
    day: str
    root: str
    entry_count: int
    external_ref: str | None = None


def compute_daily_root(org: str, day: str, day_entries: list[AuditEntry]) -> AnchorRecord:
    """Compute the anchorable daily root for ``org`` over the entries it sealed on ``day``
    (caller supplies the day's entries, already filtered — keeps this pure/DB-free)."""
    leaves = [e.this_hash for e in day_entries]
    root = hashlib.sha256(
        canonical_json({"org": org, "day": day, "leaves": leaves}).encode("utf-8")
    ).hexdigest()
    return AnchorRecord(org=org, day=day, root=root, entry_count=len(leaves))
