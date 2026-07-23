"""WS10.1 — SPA surface for the Privacy section: rights-request list + the DPDP-notice
acceptance status/accept pair.

Raising a request is NOT here: it goes through the generic action preview/commit routes
(``compliance/dpdp-request`` in ``app.web.actions``) so the drawer's preview→confirm discipline
(INVARIANT 9) applies unchanged. This router only reads, plus the one self-service acceptance
write.

RBAC: everything here is gated ``read`` at the router level. That includes POST
``/notice/accept`` deliberately: an acceptance is the verified caller binding THEMSELVES to a
published notice version — identity is the authorization (the ``/api/ca/accept`` precedent) —
and it must not be denied to read-only roles (a CA's acceptance is as real as an Owner's).
It writes only the caller's own acceptance row, attributed from the JWT, never a body field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import dpdp, legal
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.db.session import get_session
from app.web.actions import find_action
from app.web.api_domains import _field_json

router = APIRouter(
    prefix="/api/legal", tags=["legal"], dependencies=[Depends(require(Capability.READ))]
)


@router.get("/dpdp/requests")
async def dpdp_requests(db: Session = Depends(get_session)) -> dict[str, Any]:
    """This org's rights requests plus the raise-request action's field schema (the SERVER's
    registry, serialized exactly as ``GET /api/domains/{d}`` does — the SPA renders the same
    ActionDrawer from it, so the form can never drift from what the handler validates)."""
    action = find_action("compliance", "dpdp-request")
    assert action is not None  # registered in app.web.actions; a rename fails loudly here
    return {
        "requests": dpdp.list_requests(db),
        "sla_days": dpdp.SLA_DAYS,
        "action": {
            "key": action.key,
            "label": action.label,
            "fields": [_field_json(f) for f in action.fields],
        },
    }


@router.get("/notice")
async def notice_status(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """The DPDP notice in force (if any) and whether the CALLER still needs to accept it.
    While every document in docs/legal/ is a counsel-gated draft, nothing is published and
    this honestly reports no notice — never a fabricated in-force version (§0.6)."""
    now = datetime.now(UTC)
    version = legal.current_version(legal.DocType.DPDP_NOTICE, now)
    return {
        "doc_type": legal.DocType.DPDP_NOTICE.value,
        "current_version": version,
        "needs_acceptance": legal.needs_reacceptance(
            db, principal.user_id, legal.DocType.DPDP_NOTICE, now
        ),
    }


@router.post("/notice/accept")
async def notice_accept(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Record the verified caller's acceptance of the in-force DPDP notice — the EXISTING
    append-only acceptance-log mechanics (``legal.record_acceptance``), nothing new."""
    now = datetime.now(UTC)
    version = legal.current_version(legal.DocType.DPDP_NOTICE, now)
    if version is None:
        raise HTTPException(
            status_code=400,
            detail="no DPDP notice is published yet — there is nothing to accept",
        )
    row = legal.record_acceptance(db, principal.user_id, legal.DocType.DPDP_NOTICE, version, now)
    db.commit()
    return {"accepted": True, "version": row.version, "accepted_at": row.accepted_at}
