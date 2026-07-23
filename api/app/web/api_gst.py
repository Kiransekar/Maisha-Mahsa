"""P2-2 — GST detail JSON surface for the SPA (/d/gst deep flows).

Thin wrappers over EXISTING engines — nothing is recomputed here:

  * ITC reconciliation  -> ``GstService.reconcile_itc`` (the SAME aggregates the GST snapshot
    feeds Mahsa) plus the ``ItcRegister`` rows behind them. Every figure is badged through the
    one §0.4 gate (``mahsa_coverage.badge_state``) — the recon aggregates are not ported
    recompute targets today, so they honestly read ◐, never a fabricated ✓.
  * GSTR-1 / e-invoice downloads -> the SAME service calls the HTMX ``/d/gst/*.json`` artifact
    routes make (``RevenueService.gstr1_lines`` + ``gst_calc.gstr1_json``;
    ``RevenueService.einvoice``), now RBAC-gated read+export like every other /api download.
    WS9.3: the e-invoice payload carries ``DRAFT_IRN_LABEL`` (IrnStatus + QR caption) — a
    locally computed IRN is never IRP-registered and has no legal force; the label also ships
    on ``/detail`` so the SPA surface must show it (vitest-locked).
  * IMS                 -> the WS1.D4 pure state machine (``app.domains.gst.ims``). The
    recipient's accept/reject is persisted on ``ItcRegister.ims_action``; the disposition is
    ALWAYS recomputed by ``ims_disposition``, never stored.
  * QRMP / CMP-08       -> ``qrmp.filing_calendar`` for the settings-declared profile
    (``gst_filing_profile``). The statutory due-date calendar days are BLOCKED-CA (§0.6) — no
    date is injected here, so every obligation arrives ``pending_ca=true`` and the UI says
    "statutory due date pending CA", never a guessed date.

IMS deemed-accept deadline: BLOCKED-CA per ``app/domains/gst/ims.py`` — no statutory date
offset may be wired until a CA-cited vector exists. ``date.max`` is the honest "no deadline
known" injection: the deemed-accept branch can never fire, unactioned rows stay ``pending``,
and the payload states ``deadline_pending_ca`` so the UI never implies a deadline was
evaluated.

Writes are preview→confirm (INVARIANT 9): the IMS action route reuses ``api_actions``'
``preview_token`` HMAC — a commit whose (org, ids, action) was never previewed, or whose
selection changed after the preview, is a 409 and writes nothing. Preview is a pure read
(``api_bulk`` precedent); the commit additionally enforces ``write`` in-handler.
"""

from __future__ import annotations

import hmac
import json
from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.principal import Principal
from app.core.rbac import Capability, can
from app.core.rbac_deps import enforce, require, resolve_principal
from app.db.models.gst import ItcRegister
from app.db.session import get_session
from app.domains.gst import gst_calc, qrmp
from app.domains.gst.gst_calc import DRAFT_IRN_LABEL
from app.domains.gst.ims import InwardInvoice, ims_disposition
from app.domains.gst.rules import GST_RULES
from app.domains.gst.service import GstService
from app.domains.revenue.service import RevenueService
from app.web.api_actions import preview_token
from app.web.api_domains import _figure

router = APIRouter(
    prefix="/api/gst", tags=["gst-spa"], dependencies=[Depends(require(Capability.READ))]
)


def _today() -> date:
    return datetime.now(UTC).date()


# ── ITC reconciliation (a) ────────────────────────────────────────────────────────


def _mismatches(rows: list[ItcRegister]) -> list[dict[str, Any]]:
    """Every register row the GSTR-2B/books comparison disagrees on, each ₹ badged.

    ``reconcile_itc``'s aggregates net these out; here each one is NAMED so a CA can act on
    it. Two kinds, matching the aggregate's construction exactly:
      * claimed in books but absent from GSTR-2B  -> the Rule 36(4) exposure side
      * present in GSTR-2B but not claimed        -> potentially missed credit
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.eligible_itc and not r.in_2b:
            kind, note = (
                "books_not_in_2b",
                "Claimed in books, missing from GSTR-2B — Rule 36(4) exposure.",
            )
        elif r.in_2b and not r.eligible_itc:
            kind, note = (
                "in_2b_not_claimed",
                "In GSTR-2B, not claimed in books — potentially missed credit.",
            )
        else:
            continue
        out.append(
            {
                "id": r.id,
                "invoice_number": r.invoice_number,
                "gstin_supplier": r.gstin_supplier,
                "invoice_date": r.invoice_date,
                "kind": kind,
                "note": note,
                "figure": _figure("itc_mismatch_tax_paise", int(r.total_tax)),
            }
        )
    return out


# ── IMS (c) ───────────────────────────────────────────────────────────────────────

#: BLOCKED-CA (§0.6, see module docstring): "no deadline known" — deemed-accept never fires.
_NO_DEADLINE = date.max

_IMS_DEADLINE_NOTE = (
    "The GSTR-3B-linked deemed-acceptance deadline is not yet CA-sourced (BLOCKED-CA), so "
    "deemed acceptance is NOT evaluated: an unactioned invoice stays pending. No date was "
    "guessed."
)


def _ims_rows(
    rows: list[ItcRegister], as_of: date, override: dict[int, str] | None = None
) -> dict[str, Any]:
    """Disposition of every inward invoice via the WS1.D4 engine — with ``override`` a
    proposed action is applied IN MEMORY only (the preview path; nothing persisted)."""
    override = override or {}
    invs = [
        InwardInvoice(
            id=str(r.id),
            itc_paise=int(r.total_tax),
            deadline=_NO_DEADLINE,
            action=(override.get(r.id) or r.ims_action or None),  # type: ignore[arg-type]
        )
        for r in rows
    ]
    result = ims_disposition(invs, as_of=as_of)
    by_id = {r.id: r for r in rows}
    return {
        "invoices": [
            {
                **d,
                "invoice_number": by_id[int(d["id"])].invoice_number,
                "gstin_supplier": by_id[int(d["id"])].gstin_supplier,
                "invoice_date": by_id[int(d["id"])].invoice_date,
                "figure": _figure("ims_itc_paise", d["itc_paise"]),
            }
            for d in result["invoices"]
        ],
        # aggregate from the engine, badged through the one §0.4 gate like every other figure
        "eligible_itc_total": _figure(
            "ims_eligible_itc_total_paise", result["eligible_itc_total_paise"]
        ),
        "deadline_pending_ca": True,
        "deadline_note": _IMS_DEADLINE_NOTE,
    }


def _ims_token(org_id: str, action: str, ids: list[int]) -> str:
    """The preview HMAC for an IMS decision — the SAME construction api_actions commits use
    (org + domain + key + canonical values), so 'commit without preview' is rejected by
    the server's secret, not by client discipline. ids are canonicalized (sorted, deduped)
    identically on preview and commit."""
    canonical = ",".join(str(i) for i in sorted(set(ids)))
    return preview_token(org_id, "gst", "ims", {"action": action, "ids": canonical})


# ── QRMP / CMP-08 visibility (d) ─────────────────────────────────────────────────


def _quarter_months(as_of: date) -> list[str]:
    """The three "YYYY-MM" labels of the calendar quarter containing ``as_of`` (GST filing
    quarters are calendar quarters: Apr–Jun, Jul–Sep, Oct–Dec, Jan–Mar)."""
    start = ((as_of.month - 1) // 3) * 3 + 1
    return [f"{as_of.year}-{m:02d}" for m in range(start, start + 3)]


def _obligations(as_of: date) -> dict[str, Any]:
    profile = get_settings().gst_filing_profile
    # No due_dates injected: the statutory calendar days are BLOCKED-CA (§0.6) — every
    # obligation returns pending_ca=True rather than a guessed date.
    cal = qrmp.filing_calendar(profile, _quarter_months(as_of))
    return {
        **cal,
        "profile_source": "settings.gst_filing_profile",
        "due_dates_note": (
            "Statutory due dates for these obligations are not yet CA-sourced — each one is "
            "marked pending CA, never guessed."
        ),
    }


# ── routes ────────────────────────────────────────────────────────────────────────


@router.get("/detail")
def gst_detail(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Everything the SPA GST page needs beyond the generic /api/domains/gst payload."""
    as_of = _today()
    recon = GstService().reconcile_itc(db)
    rows = list(db.scalars(select(ItcRegister)).all())
    return {
        "as_of": as_of.isoformat(),
        "recon": {
            "figures": [_figure(k, v) for k, v in recon.items()],
            "rule_36_4": {
                "rule_id": "GST-002",
                "text": GST_RULES["GST-002"],
                "statute": "CGST Rules 2017",
                "section": "Rule 36(4)",
                "itc_claimed_ratio": recon["itc_claimed_ratio"],
            },
            "mismatches": _mismatches(rows),
        },
        "ims": _ims_rows(rows, as_of),
        "obligations": _obligations(as_of),
        # T11 precedent (Audit Room): download controls are HIDDEN, not disabled, without export.
        "can_export": can(principal.role, Capability.EXPORT),
        # WS9.3 — shown verbatim on every e-invoice artifact surface (vitest-locked in the SPA).
        "draft_irn_label": DRAFT_IRN_LABEL,
    }


class ImsActionBody(BaseModel):
    action: Literal["accept", "reject"]
    ids: list[int] = Field(default_factory=list)
    confirm: bool = False  # default dry-run: a preview must never mutate
    preview_token: str = ""


@router.post("/ims/action")
def ims_action(
    body: ImsActionBody,
    request: Request,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Preview-then-confirm IMS decision. ``confirm=false`` is a pure dry-run (read);
    ``confirm=true`` needs ``write`` AND the preview token for THESE exact ids+action."""
    if not body.ids:
        raise HTTPException(status_code=422, detail="No invoices selected. Nothing was changed.")
    as_of = _today()
    ids = sorted(set(body.ids))
    rows = list(db.scalars(select(ItcRegister).where(ItcRegister.id.in_(ids))).all())
    found = {r.id for r in rows}
    skipped = [
        {
            "id": missing,
            "reason": "Not in the ITC register — nothing was changed for it.",
        }
        for missing in ids
        if missing not in found
    ]

    # The engine states what each row's disposition WOULD become — same code path as commit.
    proposed = _ims_rows(rows, as_of, override=dict.fromkeys(found, body.action))
    current = _ims_rows(rows, as_of)
    cur_by_id = {c["id"]: c for c in current["invoices"]}
    changes = [
        {
            **p,
            "current_state": cur_by_id[p["id"]]["state"],
            "will_state": p["state"],
        }
        for p in proposed["invoices"]
    ]

    token = _ims_token(principal.org_id, body.action, list(found))
    if not body.confirm:
        return {
            "committed": False,
            "action": body.action,
            "rows": changes,
            "skipped": skipped,
            "eligible_itc_total_after": proposed["eligible_itc_total"],
            "deadline_pending_ca": True,
            "deadline_note": _IMS_DEADLINE_NOTE,
            "preview_token": token,
        }

    enforce(principal, Capability.WRITE, request.url.path)
    if not hmac.compare_digest(body.preview_token, token):
        raise HTTPException(
            status_code=409,
            detail=(
                "No matching preview for this exact selection — preview first, then confirm. "
                "Nothing was changed."
            ),
        )
    for r in rows:
        r.ims_action = body.action
    db.commit()
    return {
        "committed": True,
        "action": body.action,
        "rows": changes,
        "skipped": skipped,
        "eligible_itc_total_after": proposed["eligible_itc_total"],
        "deadline_pending_ca": True,
        "deadline_note": _IMS_DEADLINE_NOTE,
    }


# ── artifact downloads (b) — read + export, same gates as every other /api download ──


@router.get("/gstr1.json", dependencies=[Depends(require(Capability.EXPORT))])
def gstr1_json_download(period: str, db: Session = Depends(get_session)) -> Response:
    """The SAME artifact the HTMX ``/d/gst/gstr1.json`` route builds — one builder, two doors."""
    lines = RevenueService().gstr1_lines(db, period)
    payload = gst_calc.gstr1_json(lines, gstin=get_settings().company_gstin, filing_period=period)
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="gstr1-{period}.json"'},
    )


@router.get("/einvoice.json", dependencies=[Depends(require(Capability.EXPORT))])
def einvoice_download(invoice: str, db: Session = Depends(get_session)) -> Response:
    """The SAME e-invoice artifact as HTMX ``/d/gst/einvoice.json``. The payload itself carries
    the WS9.3 draft-IRN honesty label (``IrnStatus`` + QR ``Caption`` = ``DRAFT_IRN_LABEL``) —
    a locally computed IRN is never IRP-registered."""
    try:
        payload = RevenueService().einvoice(db, invoice, seller_gstin=get_settings().company_gstin)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="einvoice-{invoice}.json"'},
    )
