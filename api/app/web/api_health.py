"""WS7.7 — connection-health / data-staleness endpoint for the SPA (UX research T4).

Thin, like ``api_router``: the route owns the clock, the pure assembler
(``app.core.freshness``) owns the logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.freshness import build_freshness
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.session import get_session
from app.deps import get_mahsa

# WS5.1: staleness data is still org data — `read` capability required.
router = APIRouter(
    prefix="/api/health", tags=["health"], dependencies=[Depends(require(Capability.READ))]
)


@router.get("/connections")
def connections(db: Session = Depends(get_session)) -> dict[str, Any]:
    return build_freshness(db, datetime.now(UTC).date())


@router.get("/rulepack")
async def rulepack(mahsa: MahsaClient = Depends(get_mahsa)) -> dict[str, Any]:
    """WS1.E3 tenant-visible rule-pack version: only what Mahsa REPORTS it loaded. Mahsa
    unreachable => version null (unknown), never a stale or assumed echo."""
    try:
        health = await mahsa.health()
    except Exception:  # noqa: BLE001 - sidecar down is a reported state, not a crash
        return {"version": None, "channel": None}
    return {
        "version": health.get("rules_version"),
        "channel": health.get("rules_channel", "stable"),
    }
