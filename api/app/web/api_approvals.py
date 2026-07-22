"""WS7.6 — JSON approvals API: the high-stakes approve/reject flow.

The point of this surface is that a human approving money sees the figures **restated and
independently recomputed at the moment of approval** — not a summary they must trust. So the
listing does not just echo the queue: for every pending domain it re-folds that domain WITH its
Prime-Directive recompute claims and reports, per figure, whether Mahsa actually recomputed it.

Invariants carried in (docs/WS7_BUILD_CONTRACT.md):
  · A figure is ``verified`` ONLY when Mahsa recomputed it and it matched to the paisa. A figure
    Mahsa cannot recompute is ``honest_pending``; a mismatch is ``unbacked``. Approving an
    unverified figure is allowed — it is just never dressed up as a verified one.
  · Never an invented ₹: no verified figure means ``verified_total_paise: null``, never 0.
  · Honest-empty ≠ zero: a domain with no recomputable figure SAYS so (``figures_note``).
  · Mahsa down is stated (``mahsa_up: false`` + message), never absorbed into a thinner list, and
    a decision cannot be recorded at all (503) because the decision is bound to a live fold.
  · Mutations are confirm-gated: the caller must type the domain name back.

All approval logic is reused from ``app.core.approvals`` — nothing here re-derives a verdict.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.approvals import ApprovalItem, pending_approvals, record_decision
from app.core.mahsa_client import MahsaClient, MahsaError, RecomputeCheck
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.core.verdict import Figure
from app.db.models.shared import Decision
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.web.exceptions_router import _claims as domain_claims
from app.web.exceptions_router import _snapshot as domain_snapshot

router = APIRouter(prefix="/api", tags=["approvals"])

_registry = build_registry()

MAHSA_DOWN = (
    "Mahsa is unreachable, so nothing here has been independently recomputed. "
    "No approval is listed and none can be recorded until the gate is back."
)

_NO_CLAIMS = (
    "No figure in this domain is Mahsa-recomputable yet. Approving this approves an "
    "unverified position — the verdict is real, the arithmetic behind it is not sealed."
)


def _today() -> date:
    return datetime.now(UTC).date()


def _org_id() -> str:
    # ponytail: single-tenant deployment — the filer GSTIN is the only real org identity the app
    # holds. If multi-tenancy lands, this becomes the session-context org (verdict.py §0.8).
    return get_settings().company_gstin or "unregistered"


def _figure(chk: RecomputeCheck) -> dict[str, Any]:
    """One restated figure. State comes from Mahsa's check ONLY — never optimistically ✓."""
    if chk.honest_pending:
        state = "honest_pending"  # Mahsa cannot recompute this target yet (◐)
    elif chk.matches:
        state = "verified"  # recomputed and matched to the paisa (✓)
    else:
        state = "unbacked"  # recomputed and DID NOT match (✕) — a blocked figure
    return {
        "target": chk.target,
        "label": chk.label,
        "claimed_paise": int(chk.claimed_paise),
        "recomputed_paise": chk.recomputed_paise,
        "recomputed_values": chk.recomputed_values,
        "state": state,
        "note": chk.note,
    }


async def _restate(
    session: Session, mahsa: MahsaClient, item: ApprovalItem, as_of: date | None
) -> dict[str, Any]:
    """The approval item plus the figures it is really asking a human to sign off, each with the
    verification state Mahsa just produced and a verdict hash over the ones that verified."""
    service = _registry.get(item.domain)
    claims = domain_claims(service, session, as_of) if service is not None else []
    figures: list[dict[str, Any]] = []
    verdict_hash: str | None = None
    rule_pack_version: str | None = None

    if claims and service is not None:
        fold = await mahsa.fold(
            domain_snapshot(service, session, as_of),
            domain=item.domain,
            recompute_claims=claims,
        )
        rule_pack_version = fold.rules_version
        figures = [_figure(c) for c in fold.recompute]
        sealed = [
            Figure(key=c.target, value_paise=int(c.recomputed_paise))
            for c in fold.recompute
            if c.matches and c.recomputed_paise is not None
        ]
        if sealed:
            verdict_hash = fold.verdict(sealed, org_id=_org_id()).hash

    # Only single-value recomputes are summable; a multi-value check verifies field-wise and has
    # no scalar, so it counts as verified but stays out of the total.
    summable = [
        f for f in figures if f["state"] == "verified" and f["recomputed_paise"] is not None
    ]
    verified = [f for f in figures if f["state"] == "verified"]
    return {
        **asdict(item),
        "figures": figures,
        "figures_note": None if figures else _NO_CLAIMS,
        # Never invent a ₹: nothing verified => no total at all, not ₹0. (A real sum of ₹0 is a
        # genuine zero and is reported as 0.)
        "verified_total_paise": (
            sum(f["recomputed_paise"] for f in summable) if summable else None
        ),
        "verified_count": len(verified),
        "unverified_count": len(figures) - len(verified),
        "all_verified": bool(figures) and len(verified) == len(figures),
        "verdict_hash": verdict_hash,
        "rule_pack_version": rule_pack_version,
    }


@router.get("/approvals")
async def approvals_json(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    _: object = Depends(require(Capability.READ)),
) -> dict[str, Any]:
    as_of = _today()
    try:
        items = await pending_approvals(db, mahsa, _registry, as_of=as_of)
        restated = [await _restate(db, mahsa, it, as_of) for it in items if it.resolution is None]
    except MahsaError:
        return {
            "mahsa_up": False,
            "as_of": as_of.isoformat(),
            "items": [],
            "message": MAHSA_DOWN,
        }
    return {"mahsa_up": True, "as_of": as_of.isoformat(), "items": restated}


class DecideRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    confirm_text: str


@router.post("/approvals/{domain}/decide")
async def decide_json(
    domain: str,
    body: DecideRequest,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(require(Capability.APPROVE_PAYMENT)),
) -> dict[str, Any]:
    """Record an approve/reject and return the AUDIT RECEIPT (chain hash + timestamp).

    WS5.1: gated on ``approve_payment``. The queue mixes money approvals and filing approvals,
    and ``approve_payment`` / ``approve_filing`` are held by exactly the same roles
    (Owner/Admin/Approver — see ``rbac.ROLE_CAPABILITIES``), so one gate on the route is the
    same policy as a per-domain split, without pretending the route knows which it is.

    The decision is attributed to the VERIFIED caller, not to a settings default.
    """
    if body.confirm_text.strip().lower() != domain.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation did not match. Type '{domain}' to confirm. Nothing was written.",
        )
    try:
        message = await record_decision(
            db,
            domain=domain,
            decision=body.decision,
            mahsa=mahsa,
            registry=_registry,
            as_of=_today(),
            user_id=principal.user_id,
        )
    except MahsaError as exc:
        # The decision binds to a live fold — without the gate we refuse rather than seal a
        # decision against books nobody recomputed.
        raise HTTPException(status_code=503, detail=MAHSA_DOWN) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    row = db.scalars(
        select(Decision).where(Decision.domain == domain).order_by(Decision.id.desc()).limit(1)
    ).first()
    if row is None:  # pragma: no cover - record_decision commits or raises
        raise HTTPException(status_code=500, detail="decision was not persisted")
    return {
        "mahsa_up": True,
        "message": message,
        "receipt": {
            "domain": domain,
            "decision": body.decision,
            "audit_hash": row.audit_hash,
            "state_hash": row.state_hash,
            "timestamp": row.timestamp,
            "user_id": row.user_id,
        },
    }
