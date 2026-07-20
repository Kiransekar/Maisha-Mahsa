"""The Verdict object (PRD §WS3.4).

A Verdict is the sealed, hashable record of a set of Mahsa-recomputed figures. It is what UI
badges, PDF seals, and the audit chain bind to: if any sealed figure, the rule-pack version, or
the org it belongs to is later tampered with, the hash no longer matches.

The hash reuses the existing audit primitives (``audit.canonical_json`` + ``hashlib.sha256``) —
no new hashing dependency. It covers exactly ``{figures, rule_pack_version, org_id}``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.core.audit import canonical_json


@dataclass(frozen=True)
class Figure:
    key: str
    value_paise: int  # exact integer paise, never a float


@dataclass(frozen=True)
class Verdict:
    figures: list[Figure]
    rule_pack_version: str
    org_id: str
    hash: str

    def sealed_payload(self) -> dict[str, Any]:
        """The fields the hash covers (everything except the hash itself)."""
        return {
            "figures": [{"key": f.key, "value_paise": f.value_paise} for f in self.figures],
            "rule_pack_version": self.rule_pack_version,
            "org_id": self.org_id,
        }

    def is_intact(self) -> bool:
        """True iff a fresh recomputation of the hash still matches — i.e. nothing was tampered."""
        return compute_verdict_hash(self.figures, self.rule_pack_version, self.org_id) == self.hash


def compute_verdict_hash(figures: list[Figure], rule_pack_version: str, org_id: str) -> str:
    payload = {
        "figures": [{"key": f.key, "value_paise": f.value_paise} for f in figures],
        "rule_pack_version": rule_pack_version,
        "org_id": org_id,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_verdict(
    figures: list[Figure],
    rule_pack_version: str,
    *,
    org_id: str,
) -> Verdict:
    """Seal ``figures`` under ``rule_pack_version`` for a single org.

    §0.8: ``org_id`` is the **session/context** org — the caller must pass the org bound to the
    authenticated session, NEVER a value read from a request body. It is keyword-only to make an
    accidental positional pass from request data harder, and it is bound into the hash so a figure
    set sealed for one org can never be presented as another org's.
    """
    return Verdict(
        figures=list(figures),
        rule_pack_version=rule_pack_version,
        org_id=org_id,
        hash=compute_verdict_hash(figures, rule_pack_version, org_id),
    )
