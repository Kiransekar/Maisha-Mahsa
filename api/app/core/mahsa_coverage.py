"""Mahsa coverage map (MMX-1.0 §WS3.5a).

Machine-readable map of which oracle targets (`api/tests/statutory_oracle/vectors/*.yaml`)
Mahsa's Rust engine can independently recompute today, per the Prime Directive (§0.4): no
figure may show as Verified unless Mahsa recomputed it and matched to the paisa.

Source of truth is the Rust port: `dif/tests/parity.rs`'s ``PORTED`` array is where a target
graduates from "not yet recomputed" to "recomputed and parity-tested". This module only reads
the generated `mahsa_coverage.json` at the repo root (pure, no network, no Rust parsing at
runtime) — regenerate that file when `PORTED` or the oracle vectors change.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_COVERAGE_JSON = Path(__file__).resolve().parents[3] / "mahsa_coverage.json"


@lru_cache(maxsize=1)
def load_coverage() -> dict:
    """Load the coverage map. ``{"targets": {name: {"ported": bool}, ...}, ...}``."""
    with _COVERAGE_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_recomputed(target: str) -> bool:
    """True iff Mahsa (Rust) independently recomputes ``target`` (present in parity.rs PORTED)."""
    entry = load_coverage()["targets"].get(target)
    return bool(entry and entry.get("ported", False))


def badge_state(target: str) -> str:
    """ "verified" iff Mahsa recomputes ``target``; otherwise "honest_pending" (§0.4)."""
    return "verified" if is_recomputed(target) else "honest_pending"
