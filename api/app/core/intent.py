"""The Python mirror of the Intent IR (`dif/src/intent.rs`). Mahsa computes the vectors;
this module only names the dimensions and provides read-side helpers for rendering."""

from __future__ import annotations

GLOBAL_DIMS: tuple[str, ...] = (
    "cash_flow",
    "risk_exposure",
    "liquidity",
    "tax_efficiency",
    "compliance",
    "diversification",
    "currency_hedge",
    "growth",
)


def labelled(vector: list[float]) -> dict[str, float]:
    """Zip an 8-dim global vector with its dimension names."""
    if len(vector) != len(GLOBAL_DIMS):
        raise ValueError(f"expected {len(GLOBAL_DIMS)} dims, got {len(vector)}")
    return dict(zip(GLOBAL_DIMS, vector, strict=True))


def score(vector: list[float]) -> float:
    """Mean health × 100, matching `IntentVec::score` in Rust."""
    if not vector:
        return 0.0
    return max(0.0, min(100.0, (sum(vector) / len(vector)) * 100.0))
