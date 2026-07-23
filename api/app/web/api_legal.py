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
from pathlib import Path
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


def _accept(db: Session, principal: Principal, doc_type: legal.DocType) -> dict[str, Any]:
    """Record the verified caller's acceptance of the in-force version of ``doc_type`` — the
    append-only acceptance-log mechanics (``legal.record_acceptance``), shared by the DPDP
    notice route and the WS10.4 generic ToS/Privacy route."""
    now = datetime.now(UTC)
    version = legal.current_version(doc_type, now)
    if version is None:
        raise HTTPException(
            status_code=400,
            detail=f"no {doc_type.value} is published yet — there is nothing to accept",
        )
    row = legal.record_acceptance(db, principal.user_id, doc_type, version, now)
    db.commit()
    return {"accepted": True, "version": row.version, "accepted_at": row.accepted_at}


@router.post("/notice/accept")
async def notice_accept(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Record the verified caller's acceptance of the in-force DPDP notice."""
    return _accept(db, principal, legal.DocType.DPDP_NOTICE)


# --- WS10.4 — ToS/Privacy (and every other DocType) served + versioned + acceptance-logged ---

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _doc_type_or_404(doc_type: str) -> legal.DocType:
    try:
        return legal.DocType(doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"unknown document type {doc_type!r}") from exc


@router.get("/docs")
async def docs_status(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Every legal document type: the version in force (if any) and whether the CALLER still
    needs to accept it. While everything in docs/legal/ is a counsel-gated draft, nothing is
    published and every ``current_version`` is honestly null (§0.6 — a draft publishes
    nothing)."""
    now = datetime.now(UTC)
    return {
        "docs": [
            {
                "doc_type": doc.value,
                "current_version": legal.current_version(doc, now),
                "needs_acceptance": legal.needs_reacceptance(db, principal.user_id, doc, now),
            }
            for doc in legal.DocType
        ]
    }


@router.get("/docs/{doc_type}")
async def doc_serve(doc_type: str) -> dict[str, Any]:
    """Serve the IN-FORCE version of one document (WS10.4 "served"): version, effective date,
    and the document text read from the registry's ``doc_path``. 404 while nothing is
    published — a draft is never served as if it were in force."""
    doc = _doc_type_or_404(doc_type)
    now = datetime.now(UTC)
    version = legal.current_version(doc, now)
    if version is None:
        raise HTTPException(status_code=404, detail=f"no {doc.value} is published yet")
    entry = next(e for e in legal.PUBLISHED if e.doc_type == doc and e.version == version)
    path = _REPO_ROOT / entry.doc_path
    if not path.is_file():
        # A published version whose file is missing is a deploy defect — fail loud, never
        # serve an empty or substitute text as the accepted document.
        raise HTTPException(
            status_code=500, detail=f"published {doc.value} file missing from this deployment"
        )
    return {
        "doc_type": doc.value,
        "version": version,
        "effective_at": entry.effective_at.isoformat(),
        "text": path.read_text(encoding="utf-8"),
    }


@router.post("/docs/{doc_type}/accept")
async def doc_accept(
    doc_type: str,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Record the verified caller's acceptance of the in-force version of any document type —
    same identity-is-the-authorization stance as ``/notice/accept`` (see the module docstring),
    same append-only log."""
    return _accept(db, principal, _doc_type_or_404(doc_type))
