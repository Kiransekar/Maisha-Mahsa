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
from app.db.session import get_session

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/connections")
def connections(db: Session = Depends(get_session)) -> dict[str, Any]:
    return build_freshness(db, datetime.now(UTC).date())
