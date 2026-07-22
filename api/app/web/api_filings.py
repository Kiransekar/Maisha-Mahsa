"""P0-1 FILING FLOW — JSON preview→confirm wrappers over the EXISTING filing-gated writes.

The missing end of the core loop: the product computes a return, badges every figure, and then
lets an Owner/Admin RECORD the filing — never "submit" it. Three flows, all the same shape:

    POST /api/filings/<kind>/preview   (read)      compute, badge, seal attempt evidence,
                                                   return a confirm token bound to the figures
    POST /api/filings/<kind>/confirm   (read+filing hard gate) typed confirm + token check,
                                                   then the SAME service write the existing
                                                   /api/gst/gstr3b · /api/tax/tds-returns ·
                                                   /api/compliance/deadlines/{id}/file perform

Invariants carried in (docs/WS7_BUILD_CONTRACT.md + MASTER_PLAN §0.4/§0.8 + INVARIANT 9):
  · §0.4 — a figure is ``verified`` ONLY because Mahsa live-recomputed it via the existing
    ``verify_claims`` machinery and it matched to the paisa. Mahsa down => every figure
    ``honest_pending``; an unknown target => ``honest_pending``. Nothing here can fabricate a ✓.
  · INVARIANT 9 — no write without preview → typed confirm. The confirm token is a hash over
    (action, inputs, computed figures): the server recomputes it from the submitted inputs at
    confirm time, so a token minted for a different preview can never authorize this write.
  · WS5.2 — confirm routes wear the existing ``require_filing`` hard gate (Owner/Admin only,
    not configurable). The queue tells other roles WHY they cannot confirm, using the same
    ``decide_approval`` reason the gate itself would give them.
  · T5 (BUILD_CONTRACT) — this product RECORDS filings. Every receipt says so plainly and the
    attempt-evidence bundle states what it proves and what it does not.
  · §0.8 — org for verdict sealing comes from the VERIFIED principal only.
  · T12 — a form with no ported fee renders an unknown (null) amount, never an invented ₹.

Attempt evidence: preview AND confirm each seal a ``filing.*`` entry on the hash chain (the
figures shown, their badge states, verdict hash, trace id). ``GET /api/filings/evidence``
returns those entries as a JSON bundle a CFO can attach to a penalty-waiver request when a
statutory portal was down: it proves what was computed, shown and recorded, and when.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.approval_matrix import decide_approval
from app.core.audit import canonical_json
from app.core.mahsa_client import MahsaClient, MahsaError, RecomputeCheck, RecomputeClaim
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, require_filing, resolve_principal
from app.core.verdict import Figure, build_verdict
from app.core.verify import verify_claims
from app.db.models.shared import ComplianceCalendar
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.compliance.schemas import MarkFiled
from app.domains.compliance.service import ComplianceService
from app.domains.gst import gst_calc
from app.domains.gst.schemas import Gstr3bInput
from app.domains.gst.service import GstService, itc_setoff_claim
from app.domains.tax import tax_calc
from app.domains.tax.schemas import TdsReturnInput
from app.domains.tax.service import TaxService

router = APIRouter(
    prefix="/api/filings",
    tags=["filings"],
    dependencies=[Depends(require(Capability.READ))],
)

_gst = GstService()
_tax = TaxService()
_compliance = ComplianceService()

#: T5 — the one honest sentence about what a confirm actually does. Rendered on every receipt.
RECORDED_LABEL = (
    "Recorded as filed in Maisha-Mahsa — keep your portal acknowledgement. This app records "
    "filings; it does not submit them to a government portal."
)

_TOKEN_MISMATCH = (
    "This confirmation belongs to a different preview: the figures were recomputed from the "
    "inputs you submitted and they do not match what that token was minted over. Nothing was "
    "written. Re-run the preview and read the figures again before confirming."
)


def _now() -> datetime:
    return datetime.now(UTC)


def _mint_trace(trace_id: str | None) -> str:
    return trace_id or f"filing-{uuid.uuid4().hex[:12]}"


# ── pure pieces (unit-tested via the integration round trips) ────────────────────────────


def confirm_token(action: str, inputs: dict[str, Any], figures: list[dict[str, Any]]) -> str:
    """The tamper seal between preview and confirm: a hash over the action, the exact inputs,
    and the figures those inputs computed to. Recomputed server-side at confirm — a token from
    a preview with different inputs OR different computed figures cannot authorize a write."""
    basis = canonical_json(
        {
            "action": action,
            "inputs": inputs,
            "figures": [{"target": f["target"], "value_paise": f["value_paise"]} for f in figures],
        }
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _state(chk: RecomputeCheck | None) -> str:
    """§0.4: verified ONLY from a live Mahsa recompute that matched. No check (Mahsa down, or
    no recompute path for this target) falls to honest_pending — never optimistically ✓."""
    if chk is None or chk.honest_pending:
        return "honest_pending"
    return "verified" if chk.matches else "unbacked"


def _kind_of(form_name: str) -> str:
    # ponytail: name heuristic over the compliance calendar's free-text form names; good enough
    # to route a row to the right flow. Upgrade path: a typed `kind` column on the calendar.
    n = form_name.upper()
    if "GSTR-3B" in n:
        return "gstr3b"
    if "TDS" in n or "24Q" in n or "26Q" in n or "27Q" in n:
        return "tds"
    return "deadline"


def _confirm_gate_for(principal: Principal) -> tuple[bool, str | None]:
    """Whether THIS caller could clear the statutory hard gate, and if not, the exact reason the
    gate itself would give — capability-derived, never invented client-side. Any statutory
    action gives the same answer (the hard gate ignores the matrix): Owner/Admin only."""
    verdict = decide_approval("basics", principal.role, "mark_filed", 0)
    ok = bool(verdict["required_role_ok"])
    return ok, None if ok else str(verdict["reason"])


async def _checks(
    mahsa: MahsaClient, claims: list[RecomputeClaim]
) -> tuple[dict[str, RecomputeCheck], str | None, bool]:
    """target -> live Mahsa check. Mahsa unreachable => ({}, None, False): every figure then
    renders honest_pending, and the caller is told the gate did not run (never absorbed)."""
    if not claims:
        return {}, None, True
    try:
        fold = await verify_claims(mahsa, claims)
    except MahsaError:
        return {}, None, False
    return {c.target: c for c in fold.recompute}, fold.rules_version, True


_MAHSA_DOWN_NOTE = "Mahsa is unreachable — this figure was NOT independently recomputed."


def _figure(
    *,
    target: str,
    label: str,
    value_paise: int | None,
    chk: RecomputeCheck | None,
    mahsa_up: bool,
    formula: str | None = None,
    citation: str | None = None,
    inputs: list[dict[str, str]] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """One badged figure in the WS7.2 shape VerifiedNumber renders: value + state + working."""
    state = _state(chk)
    resolved_note = note or (chk.note if chk else (None if mahsa_up else _MAHSA_DOWN_NOTE))
    return {
        "target": target,
        "label": label,
        "value_paise": value_paise,  # null == "not yet known — we don't guess", NEVER ₹0
        "state": state,
        "working": {
            "inputs": inputs or [],
            "formula": formula,
            "citations": [{"text": citation}] if citation else [],
            "documents": [],
            "verdict_hash": None,  # filled with the preview's sealed verdict for ✓ figures
            "note": resolved_note,
        },
    }


def _seal(
    db: Session,
    *,
    action: str,
    domain: str,
    user_id: str,
    detail: dict[str, Any],
    status: str,
    rules_version: str | None,
) -> Any:
    """Chain a filing event (attempt evidence) onto the audit log. The detail is canonical JSON
    inside ``query`` — part of the hashed core payload, so the evidence is tamper-evident."""
    return audit_store.append(
        db,
        {
            "timestamp": _now().isoformat(),
            "action": action,
            "domain": domain,
            "user_id": user_id,
            "query": canonical_json(detail),
            "intent_global": None,
            "intent_domain": None,
            "validation_status": status,
            # audit_log.rules_version is NOT NULL; "none" states honestly that no Mahsa rule
            # pack was involved (deadline flow, or Mahsa down) rather than inventing a version.
            "rules_version": rules_version or "none",
        },
    )


def _detail(
    *,
    kind: str,
    figures: list[dict[str, Any]],
    verdict_hash: str | None,
    trace_id: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "figures": [
            {
                "target": f["target"],
                "label": f["label"],
                "value_paise": f["value_paise"],
                "state": f["state"],
            }
            for f in figures
        ],
        "verdict_hash": verdict_hash,
        "trace_id": trace_id,
        **extra,
    }


def _seal_verdict(
    checks: dict[str, RecomputeCheck], rules_version: str | None, org_id: str
) -> str | None:
    """Seal the figures Mahsa actually recomputed-and-matched into a Verdict hash. Only
    single-value matches are sealable (same rule as the approvals surface); nothing verified
    => no verdict, never a fabricated one."""
    sealed = [
        Figure(key=c.target, value_paise=int(c.recomputed_paise))
        for c in checks.values()
        if c.matches and c.recomputed_paise is not None
    ]
    if not sealed or rules_version is None:
        return None
    return build_verdict(sealed, rules_version, org_id=org_id).hash


def _preview_payload(
    *,
    kind: str,
    confirm_phrase: str,
    figures: list[dict[str, Any]],
    token: str,
    principal: Principal,
    mahsa_up: bool,
    verdict_hash: str | None,
    rules_version: str | None,
    trace_id: str,
    will_record: list[str],
) -> dict[str, Any]:
    can_confirm, denied_reason = _confirm_gate_for(principal)
    for f in figures:
        if f["state"] == "verified":
            f["working"]["verdict_hash"] = verdict_hash
    return {
        "kind": kind,
        "as_of": _now().date().isoformat(),
        "mahsa_up": mahsa_up,
        "figures": figures,
        "verdict_hash": verdict_hash,
        "rule_pack_version": rules_version,
        "confirm_phrase": confirm_phrase,
        "confirm_token": token,
        "can_confirm": can_confirm,
        "confirm_denied_reason": denied_reason,
        "will_record": will_record,
        "recorded_meaning": RECORDED_LABEL,
        "trace_id": trace_id,
        "evidence_note": "This preview was sealed to the audit chain as attempt evidence.",
    }


def _check_typed(confirm_text: str, phrase: str) -> None:
    if confirm_text.strip().lower() != phrase.strip().lower():
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation did not match. Type '{phrase}' to confirm. Nothing was written.",
        )


def _check_token(submitted: str, recomputed: str) -> None:
    if submitted != recomputed:
        raise HTTPException(status_code=409, detail=_TOKEN_MISMATCH)


def _receipt(
    *,
    kind: str,
    entry: Any,
    figures: list[dict[str, Any]],
    verdict_hash: str | None,
    mahsa_up: bool,
    trace_id: str,
    principal: Principal,
    **extra: Any,
) -> dict[str, Any]:
    """T5: the confirm result names what actually happened — recorded in THIS app, not filed on
    a government portal. ``portal_submission: false`` is structural, not just copy."""
    return {
        "recorded": True,
        "recorded_as": "recorded_in_app",
        "portal_submission": False,
        "label": RECORDED_LABEL,
        "kind": kind,
        "audit_hash": entry.this_hash,
        "timestamp": entry.timestamp,
        "user_id": principal.user_id,
        "figures": figures,
        "verdict_hash": verdict_hash,
        "mahsa_up": mahsa_up,
        "trace_id": trace_id,
        "evidence_url": "/api/filings/evidence",
        **extra,
    }


# ── GSTR-3B ──────────────────────────────────────────────────────────────────────────────


def _gstr3b_days_late(body: Gstr3bInput) -> int:
    if not body.filed_date:
        return 0
    return max(0, (date.fromisoformat(body.filed_date) - date.fromisoformat(body.due_date)).days)


def _gstr3b_figures(body: Gstr3bInput) -> tuple[list[RecomputeClaim], Any]:
    """Compute the return WITHOUT persisting anything, via the same ``gst_calc`` the real write
    uses — the preview shows exactly what confirm will record."""
    days_late = _gstr3b_days_late(body)
    output = body.output.model_dump()
    itc = body.itc_available.model_dump()
    comp = gst_calc.compute_gstr3b(output, itc, days_late=days_late, is_nil=body.is_nil)
    claims = [
        itc_setoff_claim(output, itc, comp["cash"], comp["remaining_credit"]),
        RecomputeClaim(
            target="late_fee_3b",
            inputs={"days_late": days_late, "is_nil": body.is_nil},
            claimed_paise=int(comp["late_fee"]),
            label="gst.gstr3b.late_fee",
        ),
        RecomputeClaim(
            target="interest_3b",
            inputs={"cash_tax": int(comp["cash_total"]), "days_late": days_late},
            claimed_paise=int(comp["interest"]),
            label="gst.gstr3b.interest",
        ),
    ]

    def build(checks: dict[str, RecomputeCheck], mahsa_up: bool) -> list[dict[str, Any]]:
        heads = [
            {"label": h.upper(), "value": str(comp["cash"][h])} for h in ("igst", "cgst", "sgst")
        ]
        return [
            _figure(
                target="itc_setoff",
                label="Cash payable after ITC set-off",
                value_paise=int(comp["cash_total"]),
                chk=checks.get("itc_setoff"),
                mahsa_up=mahsa_up,
                formula="output tax − ITC, cash-minimizing statutory set-off order",
                citation="CGST Act s.49(5)/49A/49B r/w Rule 88A",
                inputs=heads,
            ),
            _figure(
                target="late_fee_3b",
                label="Late fee" + (f" ({days_late} days late)" if days_late else ""),
                value_paise=int(comp["late_fee"]),
                chk=checks.get("late_fee_3b"),
                mahsa_up=mahsa_up,
                formula="per-day late fee × days late, statutory cap applied",
                citation="CGST Act s.47",
                inputs=[{"label": "days late", "value": str(days_late)}],
            ),
            _figure(
                target="interest_3b",
                label="Interest on cash tax",
                value_paise=int(comp["interest"]),
                chk=checks.get("interest_3b"),
                mahsa_up=mahsa_up,
                formula="cash tax × 18% p.a. × days late / 365",
                citation="CGST Act s.50(1)",
                inputs=[
                    {"label": "cash tax (paise)", "value": str(comp["cash_total"])},
                    {"label": "days late", "value": str(days_late)},
                ],
            ),
            _figure(
                target="total_payable",
                label="Total payable",
                value_paise=int(comp["total_payable"]),
                chk=None,
                mahsa_up=mahsa_up,
                note=(
                    "Sum of the three figures above — not an independent recompute target, so it "
                    "is never shown ✓; the parts are individually recomputed."
                ),
            ),
        ]

    return claims, build


@router.post("/gstr3b/preview")
async def gstr3b_preview(
    body: Gstr3bInput,
    trace_id: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    claims, build = _gstr3b_figures(body)
    checks, rules_version, mahsa_up = await _checks(mahsa, claims)
    figures = build(checks, mahsa_up)
    verdict_hash = _seal_verdict(checks, rules_version, principal.org_id)
    trace = _mint_trace(trace_id)
    token = confirm_token("gstr3b", body.model_dump(), figures)
    _seal(
        db,
        action="filing.preview",
        domain="gst",
        user_id=principal.user_id,
        detail=_detail(
            kind="gstr3b",
            figures=figures,
            verdict_hash=verdict_hash,
            trace_id=trace,
            filing_period=body.filing_period,
            due_date=body.due_date,
            filed_date=body.filed_date,
        ),
        status="previewed",
        rules_version=rules_version,
    )
    db.commit()
    return _preview_payload(
        kind="gstr3b",
        confirm_phrase="GSTR-3B",
        figures=figures,
        token=token,
        principal=principal,
        mahsa_up=mahsa_up,
        verdict_hash=verdict_hash,
        rules_version=rules_version,
        trace_id=trace,
        will_record=[
            f"A GSTR-3B return row for {body.filing_period} "
            f"({'filed ' + body.filed_date if body.filed_date else 'pending'}) "
            "with the figures above",
            "A hash-chained audit entry sealing these figures, "
            "their badge states and this trace id",
        ],
    )


class Gstr3bConfirm(BaseModel):
    inputs: Gstr3bInput
    confirm_token: str
    confirm_text: str
    trace_id: str | None = None


@router.post("/gstr3b/confirm", dependencies=[Depends(require_filing("gstr3b"))])
async def gstr3b_confirm(
    body: Gstr3bConfirm,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    _check_typed(body.confirm_text, "GSTR-3B")
    claims, build = _gstr3b_figures(body.inputs)
    # Re-verify live so the receipt's verdict is OURS, computed now — never echoed from the client.
    checks, rules_version, mahsa_up = await _checks(mahsa, claims)
    figures = build(checks, mahsa_up)
    _check_token(body.confirm_token, confirm_token("gstr3b", body.inputs.model_dump(), figures))
    verdict_hash = _seal_verdict(checks, rules_version, principal.org_id)
    trace = _mint_trace(body.trace_id)

    result = _gst.file_gstr3b(
        db,
        filing_period=body.inputs.filing_period,
        due_date=body.inputs.due_date,
        output=body.inputs.output.model_dump(),
        itc_available=body.inputs.itc_available.model_dump(),
        filed_date=body.inputs.filed_date,
        is_nil=body.inputs.is_nil,
    )
    entry = _seal(
        db,
        action="filing.recorded",
        domain="gst",
        user_id=principal.user_id,
        detail=_detail(
            kind="gstr3b",
            figures=figures,
            verdict_hash=verdict_hash,
            trace_id=trace,
            filing_period=body.inputs.filing_period,
            gst_return_id=result["gst_return_id"],
        ),
        status="recorded",
        rules_version=rules_version,
    )
    db.commit()
    return _receipt(
        kind="gstr3b",
        entry=entry,
        figures=figures,
        verdict_hash=verdict_hash,
        mahsa_up=mahsa_up,
        trace_id=trace,
        principal=principal,
        gst_return_id=result["gst_return_id"],
        filing_period=body.inputs.filing_period,
    )


# ── TDS return ───────────────────────────────────────────────────────────────────────────


def _tds_figures(body: TdsReturnInput) -> tuple[list[RecomputeClaim], Any]:
    days_late = 0
    if body.filed_date:
        days_late = max(
            0, (date.fromisoformat(body.filed_date) - date.fromisoformat(body.due_date)).days
        )
    late_fee = tax_calc.late_fee_234e(days_late, body.total_deducted)
    claims = [
        RecomputeClaim(
            target="late_fee_234e",
            inputs={"days_late": days_late, "tds_amount": int(body.total_deducted)},
            claimed_paise=int(late_fee),
            label=f"tax.tds_{body.return_type}.late_fee_234e",
        )
    ]

    def build(checks: dict[str, RecomputeCheck], mahsa_up: bool) -> list[dict[str, Any]]:
        return [
            _figure(
                target="total_deducted",
                label=f"TDS deducted ({body.return_type} {body.quarter})",
                value_paise=int(body.total_deducted),
                chk=None,
                mahsa_up=mahsa_up,
                note="Amount as entered — recorded as given, not a recomputed figure.",
            ),
            _figure(
                target="late_fee_234e",
                label="Late filing fee" + (f" ({days_late} days late)" if days_late else ""),
                value_paise=int(late_fee),
                chk=checks.get("late_fee_234e"),
                mahsa_up=mahsa_up,
                formula="₹200 per day late, capped at the TDS amount",
                citation="Income-tax Act s.234E",
                inputs=[
                    {"label": "days late", "value": str(days_late)},
                    {"label": "TDS amount (paise)", "value": str(body.total_deducted)},
                ],
            ),
        ]

    return claims, build


@router.post("/tds/preview")
async def tds_preview(
    body: TdsReturnInput,
    trace_id: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    claims, build = _tds_figures(body)
    checks, rules_version, mahsa_up = await _checks(mahsa, claims)
    figures = build(checks, mahsa_up)
    verdict_hash = _seal_verdict(checks, rules_version, principal.org_id)
    trace = _mint_trace(trace_id)
    token = confirm_token("tds_returns", body.model_dump(), figures)
    _seal(
        db,
        action="filing.preview",
        domain="tax",
        user_id=principal.user_id,
        detail=_detail(
            kind="tds",
            figures=figures,
            verdict_hash=verdict_hash,
            trace_id=trace,
            return_type=body.return_type,
            quarter=body.quarter,
            due_date=body.due_date,
            filed_date=body.filed_date,
        ),
        status="previewed",
        rules_version=rules_version,
    )
    db.commit()
    return _preview_payload(
        kind="tds",
        confirm_phrase=body.return_type,
        figures=figures,
        token=token,
        principal=principal,
        mahsa_up=mahsa_up,
        verdict_hash=verdict_hash,
        rules_version=rules_version,
        trace_id=trace,
        will_record=[
            f"A {body.return_type} TDS return row for {body.quarter} "
            f"({'filed ' + body.filed_date if body.filed_date else 'pending'}) "
            "with the figures above",
            "A hash-chained audit entry sealing these figures, "
            "their badge states and this trace id",
        ],
    )


class TdsConfirm(BaseModel):
    inputs: TdsReturnInput
    confirm_token: str
    confirm_text: str
    trace_id: str | None = None


@router.post("/tds/confirm", dependencies=[Depends(require_filing("tds_returns"))])
async def tds_confirm(
    body: TdsConfirm,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    _check_typed(body.confirm_text, body.inputs.return_type)
    claims, build = _tds_figures(body.inputs)
    checks, rules_version, mahsa_up = await _checks(mahsa, claims)
    figures = build(checks, mahsa_up)
    _check_token(
        body.confirm_token, confirm_token("tds_returns", body.inputs.model_dump(), figures)
    )
    verdict_hash = _seal_verdict(checks, rules_version, principal.org_id)
    trace = _mint_trace(body.trace_id)

    result = _tax.file_tds_return(
        db,
        return_type=body.inputs.return_type,
        quarter=body.inputs.quarter,
        due_date=body.inputs.due_date,
        total_deducted=body.inputs.total_deducted,
        filed_date=body.inputs.filed_date,
    )
    entry = _seal(
        db,
        action="filing.recorded",
        domain="tax",
        user_id=principal.user_id,
        detail=_detail(
            kind="tds",
            figures=figures,
            verdict_hash=verdict_hash,
            trace_id=trace,
            return_type=body.inputs.return_type,
            quarter=body.inputs.quarter,
            tds_return_id=result["tds_return_id"],
        ),
        status="recorded",
        rules_version=rules_version,
    )
    db.commit()
    return _receipt(
        kind="tds",
        entry=entry,
        figures=figures,
        verdict_hash=verdict_hash,
        mahsa_up=mahsa_up,
        trace_id=trace,
        principal=principal,
        tds_return_id=result["tds_return_id"],
        quarter=body.inputs.quarter,
    )


# ── Generic compliance deadline (mark filed) ─────────────────────────────────────────────


def _deadline_or_404(db: Session, deadline_id: int) -> ComplianceCalendar:
    row = db.get(ComplianceCalendar, deadline_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"compliance deadline {deadline_id} not found")
    return row


def _deadline_figures(row: ComplianceCalendar) -> list[dict[str, Any]]:
    """T12: no ported fee schedule for arbitrary calendar forms — the amount is UNKNOWN (null),
    stated as such, never an invented ₹."""
    return [
        _figure(
            target="portal_fee",
            label=f"Late fee / penalty for {row.form_name}",
            value_paise=None,
            chk=None,
            mahsa_up=True,
            note=(
                "No ported fee schedule for this form — not yet known; we don't guess. "
                "The portal's own computation governs."
            ),
        )
    ]


def _deadline_token_inputs(row: ComplianceCalendar, body: MarkFiled) -> dict[str, Any]:
    # The row's identity fields are in the token: if the deadline row itself changed between
    # preview and confirm, the token no longer matches.
    return {
        "deadline_id": row.id,
        "form_name": row.form_name,
        "due_date": row.due_date,
        "filed_date": body.filed_date,
        "acknowledgement": body.acknowledgement,
    }


@router.post("/deadline/{deadline_id}/preview")
async def deadline_preview(
    deadline_id: int,
    body: MarkFiled,
    trace_id: str | None = None,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    row = _deadline_or_404(db, deadline_id)
    figures = _deadline_figures(row)
    trace = _mint_trace(trace_id)
    token = confirm_token("mark_filed", _deadline_token_inputs(row, body), figures)
    _seal(
        db,
        action="filing.preview",
        domain=row.domain,
        user_id=principal.user_id,
        detail=_detail(
            kind="deadline",
            figures=figures,
            verdict_hash=None,
            trace_id=trace,
            deadline_id=row.id,
            form_name=row.form_name,
            due_date=row.due_date,
            filed_date=body.filed_date,
        ),
        status="previewed",
        rules_version=None,
    )
    db.commit()
    return _preview_payload(
        kind="deadline",
        confirm_phrase=row.form_name,
        figures=figures,
        token=token,
        principal=principal,
        mahsa_up=True,  # no figure here needed Mahsa; nothing is claimed verified either way
        verdict_hash=None,
        rules_version=None,
        trace_id=trace,
        will_record=[
            f"Deadline '{row.form_name}' (due {row.due_date}) marked filed on {body.filed_date}"
            + (f" with acknowledgement {body.acknowledgement}" if body.acknowledgement else ""),
            "A hash-chained audit entry sealing this record and this trace id",
        ],
    )


class DeadlineConfirm(BaseModel):
    inputs: MarkFiled
    confirm_token: str
    confirm_text: str
    trace_id: str | None = None


@router.post(
    "/deadline/{deadline_id}/confirm", dependencies=[Depends(require_filing("mark_filed"))]
)
async def deadline_confirm(
    deadline_id: int,
    body: DeadlineConfirm,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    row = _deadline_or_404(db, deadline_id)
    _check_typed(body.confirm_text, row.form_name)
    figures = _deadline_figures(row)
    _check_token(
        body.confirm_token,
        confirm_token("mark_filed", _deadline_token_inputs(row, body.inputs), figures),
    )
    trace = _mint_trace(body.trace_id)

    _compliance.mark_filed(
        db,
        deadline_id,
        filed_date=body.inputs.filed_date,
        acknowledgement=body.inputs.acknowledgement,
    )
    entry = _seal(
        db,
        action="filing.recorded",
        domain=row.domain,
        user_id=principal.user_id,
        detail=_detail(
            kind="deadline",
            figures=figures,
            verdict_hash=None,
            trace_id=trace,
            deadline_id=row.id,
            form_name=row.form_name,
            filed_date=body.inputs.filed_date,
            acknowledgement=body.inputs.acknowledgement,
        ),
        status="recorded",
        rules_version=None,
    )
    db.commit()
    return _receipt(
        kind="deadline",
        entry=entry,
        figures=figures,
        verdict_hash=None,
        mahsa_up=True,
        trace_id=trace,
        principal=principal,
        deadline_id=row.id,
        form_name=row.form_name,
    )


# ── The queue ────────────────────────────────────────────────────────────────────────────


@router.get("")
def filings_queue(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Every not-yet-filed obligation on the compliance calendar, due or overdue, oldest first.
    Readable by every reading role — the CONFIRM is what the hard gate protects, and the queue
    says so per caller rather than hiding the button."""
    today = _now().date()
    can_confirm, denied_reason = _confirm_gate_for(principal)
    rows = db.scalars(
        select(ComplianceCalendar)
        .where(ComplianceCalendar.status != "filed")
        .order_by(ComplianceCalendar.due_date.asc())
    ).all()
    items = []
    for r in rows:
        delta = (date.fromisoformat(r.due_date) - today).days
        items.append(
            {
                "id": r.id,
                "domain": r.domain,
                "form_name": r.form_name,
                "filing_period": r.filing_period,
                "due_date": r.due_date,
                "status": r.status,
                "days_overdue": max(0, -delta),
                "due_in_days": max(0, delta),
                "kind": _kind_of(r.form_name),
            }
        )
    return {
        "as_of": today.isoformat(),
        "can_confirm": can_confirm,
        "confirm_denied_reason": denied_reason,
        "items": items,
    }


# ── Attempt evidence (T5) ────────────────────────────────────────────────────────────────


@router.get("/evidence", dependencies=[Depends(require(Capability.VIEW_AUDIT))])
def attempt_evidence(db: Session = Depends(get_session)) -> dict[str, Any]:
    """The penalty-waiver bundle: every sealed ``filing.*`` event — timestamps, the figures that
    were shown with their badge states, verdict hashes, trace ids — straight off the hash chain.
    Honest about its own limits: it proves computation/recording, never portal submission."""
    events = []
    for e in audit_store.load_chain(db):
        if not e.action.startswith("filing."):
            continue
        try:
            detail: Any = json.loads(e.query) if e.query else None
        except ValueError:
            detail = e.query
        events.append(
            {
                "timestamp": e.timestamp,
                "action": e.action,
                "domain": e.domain,
                "user_id": e.user_id,
                "status": e.validation_status,
                "detail": detail,
                "audit_hash": e.this_hash,
                "prev_hash": e.prev_hash,
            }
        )
    return {
        "generated_at": _now().isoformat(),
        "purpose": (
            "Attempt evidence for a penalty-waiver request: what was computed, shown to the "
            "filer, and recorded — with timestamps sealed in a hash chain."
        ),
        "what_this_proves": (
            "Each event below was sealed onto Maisha-Mahsa's append-only audit chain at the "
            "stated timestamp; the figures, badge states, verdict hashes and trace ids are "
            "inside the hashed payload and cannot be altered after the fact."
        ),
        "what_this_does_not_prove": (
            "Submission on any government portal. This product records filings; the portal "
            "acknowledgement remains the statutory proof of filing."
        ),
        "event_count": len(events),
        "events": events,
    }
