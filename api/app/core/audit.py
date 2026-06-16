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


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def verify_chain(entries: list[AuditEntry]) -> bool:
    """True iff the chain is intact: each entry links to the previous and its hash matches
    a fresh recomputation. An empty chain is trivially valid."""
    prev = GENESIS_HASH
    for e in entries:
        if e.prev_hash != prev:
            return False
        if compute_hash(prev, e.core_payload()) != e.this_hash:
            return False
        prev = e.this_hash
    return True
