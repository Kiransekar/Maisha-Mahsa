"""Verified-figure flow (§0.4 / the Golden Rule): send an on-demand recompute claim to Mahsa and
report whether the figure verified to the paisa.

Batch figures reach Mahsa's gate through ``run_loop`` (which folds a domain snapshot with its
``recompute_claims``). On-demand figures — 234B/234C interest, 115BAA company tax — are computed
per call and have no snapshot to fold, so this is the single path by which they reach the gate:
compute → attach a claim (see the tax service hooks) → ``verify_figure`` → verdict. A recomputable
mismatch BLOCKs (Mahsa returns red + MAHSA-PARITY-001); an unrecomputable target is honest-pending.
Mahsa being unreachable raises ``MahsaError`` — we never pass a figure off as verified when the
gate did not run.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.mahsa_client import FoldResult, MahsaClient, RecomputeCheck, RecomputeClaim

MAHSA_PARITY_RULE = "MAHSA-PARITY-001"


class FigureVerdict(BaseModel):
    verified: bool  # Mahsa recomputed the figure AND it matched to the paisa
    blocked: bool  # a recomputable mismatch fired the Prime-Directive block
    honest_pending: bool  # Mahsa cannot recompute this target yet (render ◐, not ✓/✕)
    check: RecomputeCheck | None = None


def _blocked(fold: FoldResult) -> bool:
    return any(t.id == MAHSA_PARITY_RULE for t in fold.validation.triggered)


async def verify_figure(
    mahsa: MahsaClient, claim: RecomputeClaim, *, snapshot: dict[str, Any] | None = None
) -> FigureVerdict:
    """Send one on-demand ``claim`` to Mahsa and return whether it verified. The snapshot is
    irrelevant to the recompute gate (defaults to empty); no domain is folded so only the
    Prime-Directive check drives the verdict."""
    fold = await mahsa.fold(snapshot or {}, recompute_claims=[claim])
    check = fold.recompute[0] if fold.recompute else None
    return FigureVerdict(
        verified=bool(check and check.matches),
        blocked=_blocked(fold),
        honest_pending=bool(check and check.honest_pending),
        check=check,
    )


async def verify_claims(
    mahsa: MahsaClient, claims: list[RecomputeClaim], *, snapshot: dict[str, Any] | None = None
) -> FoldResult:
    """Send several on-demand claims at once; returns the raw ``FoldResult`` (inspect
    ``.recompute`` per claim and ``.validation`` for the block). Empty ``claims`` still folds."""
    return await mahsa.fold(snapshot or {}, recompute_claims=claims or None)
