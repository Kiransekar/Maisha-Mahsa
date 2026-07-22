"""JSON API for the React SPA (frontend/). Deliberately thin: it reuses the SAME pure assemblers
the HTMX pages render (``build_today`` / ``build_inbox``) and the same Mahsa-backed collectors, so
the SPA and the server-rendered app can never drift into two different truths.

Honesty invariant carried over unchanged: when Mahsa is down we return the honest-empty view with
``mahsa_up: false`` — never a figure that looks verified without a live recompute gate.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.approvals import pending_approvals
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.web.exceptions import build_inbox, build_items
from app.web.exceptions_router import collect_sources
from app.web.today import build_today

# WS5.1: read-only SPA surface — every route needs the `read` capability of a verified caller.
router = APIRouter(prefix="/api", tags=["spa"], dependencies=[Depends(require(Capability.READ))])

_registry = build_registry()


@router.get("/today")
async def today_json(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict[str, Any]:
    as_of = datetime.now(UTC).date()
    try:
        approvals = await pending_approvals(db, mahsa, _registry, as_of=as_of)
        mahsa_up = True
    except MahsaError:
        approvals = []
        mahsa_up = False
    return {**build_today(db, as_of, approvals), "mahsa_up": mahsa_up}


@router.get("/inbox")
async def inbox_json(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict[str, Any]:
    as_of = datetime.now(UTC).date()
    try:
        approvals, blocked, mahsa_up = await collect_sources(db, mahsa, as_of)
        inbox = build_inbox(build_items(approvals, blocked))
    except MahsaError:
        mahsa_up = False
        inbox = build_inbox([])
    # ponytail: asdict drops the count/total properties — the SPA derives them from items.length.
    return {"mahsa_up": mahsa_up, "as_of": as_of.isoformat(), **asdict(inbox)}
