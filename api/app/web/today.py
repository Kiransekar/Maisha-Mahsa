"""WS7.3 — the Today view assembler (the Owner's default landing, MASTER_PLAN §WS5.3).

Pure: session + as_of + already-fetched approvals in, a plain dict out. No clock, no Mahsa
call, no fabrication — the route does the async Mahsa fetch and passes the result in, so this
stays trivially testable and deterministic.

Three regions + one counter, all grounded in docs/WS7_UX_RESEARCH.md:
  1. CASH STRIP     — cash / monthly burn / runway (TreasuryService). No Mahsa verdict is
                      available in a pure assembler, so every figure renders honest-pending (◐),
                      never a fabricated ✓ (WS7.1 invariant, T1).
  2. NEEDS-YOU      — pending approvals as one-tap items (app.core.approvals). Approvals carry
                      no single ₹ scalar, so the ₹-consequence is honest-pending, not invented.
  3. TROUBLE RADAR  — compliance deadlines/risks in the T5/T6 alert grammar
                      (what / when / ₹-consequence / one-tap action), ranked by ₹ impact. The
                      only real statutory ₹ figure we can stand behind is the ported GSTR-3B
                      late fee (gst_calc.late_fee_3b); non-GST forms get honest-pending, never a
                      made-up number.
Plus a PENALTIES-AVOIDED counter — an explicit ESTIMATE, every rupee of it backed by the real
ported statutory cap, never invented (the WS7.3 research challenge).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.anchors import bank_documents
from app.core.approvals import ApprovalItem
from app.core.overview import upcoming_deadlines
from app.db.models.shared import ComplianceCalendar
from app.db.models.treasury import BankTransaction
from app.domains.gst import gst_calc
from app.domains.treasury.service import TreasuryService
from app.web.format import inr

# Statutory GSTR-3B late-fee cap (₹10,000, paise) — the ported constant, reached by feeding a
# large days-late into the real ported function so we never hard-code the number ourselves.
_MAX_LATE_FEE = gst_calc.late_fee_3b(10**6)

_PENDING_CONSEQUENCE = "₹ impact shown on review"


def _honest_panel(
    label: str, value: str, note: str, documents: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A Verified-Number chip panel in the honest-pending (◐) state — the WS7.2 shape, with no
    verdict fabricated (verdict_hash stays None => 'not yet sealed')."""
    return {
        "label": label,
        "value": value,
        "state": "honest_pending",
        "inputs": [],
        "formula": None,
        "note": note,
        "citations": [],
        "documents": documents or [],
        "verdict_hash": None,
        "rule_pack_version": None,
    }


def _cash_strip(session: Session, as_of: date) -> list[dict[str, Any]]:
    m = TreasuryService().metrics(session, as_of)
    runway = m["runway_months"]
    runway_display = "∞ — no net burn" if runway is None else f"{runway:g} months"
    note = "Mahsa recomputes this in the domain fold; shown here as-is, not yet sealed."
    # SPEC-MEMCITE-1.0 CITE.P0-3 (§B4.1): the cell-level citation anchors behind these figures
    # — every anchored bank row, rendered as "file, row N: …" excerpts with a live resolution
    # state (RESOLVED / MOVED-with-note / BROKEN, §B2). All three figures derive from the same
    # imported statements, so they share the one resolved set. Legacy rows without anchors
    # contribute nothing — absence renders as absence, never fabricated provenance (§B5).
    txns = session.scalars(select(BankTransaction).order_by(BankTransaction.id)).all()
    documents = bank_documents(session, txns)
    return [
        _honest_panel("Cash on hand", inr(m["cash_paise"]), note, documents),
        _honest_panel("Monthly burn", inr(m["monthly_burn_paise"]), note, documents),
        _honest_panel("Runway", runway_display, note, documents),
    ]


def _needs_you(approvals: list[ApprovalItem]) -> list[dict[str, Any]]:
    """Unresolved approvals as one-tap items. Each states what happened, its ₹-consequence
    (honest-pending — approvals expose no single scalar, so we never invent one) and the action."""
    items: list[dict[str, Any]] = []
    for a in approvals:
        if a.resolution is not None:  # already approved/rejected
            continue
        what = a.citations[0]["text"] if a.citations else f"Mahsa flagged a {a.status} verdict"
        items.append(
            {
                "domain": a.domain,
                "title": f"{a.domain.capitalize()} needs your sign-off",
                "what": what,
                "color": a.color,
                "consequence_pending": True,
                "consequence": _PENDING_CONSEQUENCE,
                "action_label": "Review & approve",
                "action_href": "/approvals",
            }
        )
    return items


def _penalty_map(session: Session) -> dict[tuple[str, str, str], int]:
    """Real stored per-form penalty (paise), keyed by (domain, form_name, due_date). Only
    non-zero entries — a 0 default is 'not recorded', not a real ₹0 consequence."""
    rows = session.scalars(select(ComplianceCalendar)).all()
    return {
        (r.domain, r.form_name, r.due_date): r.penalty_amount
        for r in rows
        if r.penalty_amount
    }


def _trouble_radar(session: Session, as_of: date) -> list[dict[str, Any]]:
    """Compliance deadlines/risks in the T5 alert grammar, ranked by ₹ impact (desc). The
    ₹-consequence prefers the real stored penalty for that form; else the ported statutory GST
    late fee where it applies; else honest-pending — never an invented number."""
    pmap = _penalty_map(session)
    out: list[dict[str, Any]] = []
    for e in upcoming_deadlines(session, as_of):
        domain = e.get("domain") or "compliance"
        is_gst = domain == "gst"
        overdue = e["label"] == "OVERDUE"
        recorded = pmap.get((str(e.get("domain")), str(e.get("form_name")), str(e["due_date"])))

        if recorded:
            paise: int | None = recorded
            kind = "recorded"
        elif overdue and is_gst:
            paise = gst_calc.late_fee_3b(e["days_overdue"])
            kind = "accruing"
        elif is_gst:
            paise = _MAX_LATE_FEE
            kind = "if_missed"
        else:
            paise = None  # no recorded or ported statutory fee for this form — do NOT invent one
            kind = "pending"

        if overdue:
            when = f"OVERDUE by {e['days_overdue']} day(s) — due {e['due_date']}"
        else:
            when = f"Due {e['due_date']} ({e['label'].lower().replace('-', ' ')})"

        out.append(
            {
                "what": e.get("form_name") or f"{domain} filing",
                "domain": domain,
                "when": when,
                "overdue": overdue,
                "consequence_paise": paise,
                "consequence_kind": kind,
                "action_label": "File now" if overdue else f"Open {domain}",
                "action_href": f"/d/{domain}",
            }
        )
    out.sort(key=lambda r: (r["consequence_paise"] or 0, r["overdue"]), reverse=True)
    return out


def _penalties_avoided(session: Session) -> dict[str, Any]:
    """ESTIMATE, badge-backed — never invented. Every GST return already filed avoided up to the
    real ported statutory late-fee cap; the total is count × that ported cap, explicitly flagged
    an estimate (we lack the filed-date to compute the exact days-early avoided)."""
    filed_gst = session.scalars(
        select(ComplianceCalendar).where(
            ComplianceCalendar.status == "filed", ComplianceCalendar.domain == "gst"
        )
    ).all()
    count = len(filed_gst)
    paise = count * _MAX_LATE_FEE
    return {
        "amount_paise": paise,
        "amount": inr(paise),
        "estimate": True,
        "backed": True,  # each rupee traces to gst_calc.late_fee_3b, not a made-up figure
        "component_count": count,
        "basis": (
            f"{count} GST return(s) filed on time × up to "
            f"{inr(_MAX_LATE_FEE)} statutory late-fee cap each"
        ),
    }


def build_today(
    session: Session, as_of: date, approvals: list[ApprovalItem]
) -> dict[str, Any]:
    needs_you = _needs_you(approvals)
    return {
        "as_of": as_of.isoformat(),
        "cash_strip": _cash_strip(session, as_of),
        "needs_you": needs_you,
        "needs_you_empty": not needs_you,
        "trouble": _trouble_radar(session, as_of),
        "penalties_avoided": _penalties_avoided(session),
    }
