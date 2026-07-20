"""GST service: GSTR-3B computation/persistence, GSTR-1 summary, ITC reconciliation, and
the GST health snapshot for Mahsa. Exact paise; deterministic (``as_of`` injected)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.core.mahsa_client import RecomputeClaim
from app.db.models.gst import GstReturn, ItcRegister
from app.domains.gst import gst_calc
from app.domains.gst.manifest import MANIFEST


def _days_between(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


class GstService(BaseDomainService):
    domain = "gst"
    keywords = ("gst", "gstr", "gstr-1", "gstr-3b", "itc", "e-invoice", "irn", "hsn", "gstin")
    manifest = MANIFEST

    # ---- GSTR-3B --------------------------------------------------------------------

    def file_gstr3b(
        self,
        session: Session,
        *,
        filing_period: str,
        due_date: str,
        output: dict[str, int],
        itc_available: dict[str, int],
        filed_date: str | None = None,
        is_nil: bool = False,
    ) -> dict[str, Any]:
        days_late = max(0, _days_between(filed_date, due_date)) if filed_date else 0
        comp = gst_calc.compute_gstr3b(output, itc_available, days_late=days_late, is_nil=is_nil)
        ret = GstReturn(
            return_type="GSTR-3B",
            filing_period=filing_period,
            due_date=due_date,
            filed_date=filed_date,
            status="filed" if filed_date else "pending",
            tax_payable=int(comp["cash_total"]),
            tax_paid=int(comp["total_payable"]) if filed_date else 0,
            late_fee=int(comp["late_fee"]),
            interest=int(comp["interest"]),
        )
        session.add(ret)
        session.flush()
        return {
            "gst_return_id": ret.id,
            "filing_period": filing_period,
            "cash": comp["cash"],
            "cash_total": comp["cash_total"],
            "late_fee": comp["late_fee"],
            "interest": comp["interest"],
            "total_payable": comp["total_payable"],
        }

    # ---- GSTR-1 ---------------------------------------------------------------------

    def build_gstr1(self, lines: list[dict], *, filing_period: str) -> dict[str, Any]:
        return gst_calc.build_gstr1(lines, filing_period=filing_period)

    # ---- ITC reconciliation ---------------------------------------------------------

    def reconcile_itc(self, session: Session) -> dict[str, Any]:
        rows = session.scalars(select(ItcRegister)).all()
        available_2b = sum(int(r.total_tax) for r in rows if r.in_2b and r.eligible_itc)
        claimed = sum(int(r.total_tax) for r in rows if r.eligible_itc)
        ratio = (claimed / available_2b) if available_2b > 0 else 1.0
        gap = abs(claimed - available_2b)
        return {
            "available_2b_paise": available_2b,
            "claimed_paise": claimed,
            "itc_claimed_ratio": round(ratio, 6),
            "gap_paise": gap,
        }

    # ---- Mahsa contract -------------------------------------------------------------

    def recompute_claims(
        self, session: Session, as_of: date | None = None
    ) -> list[RecomputeClaim]:
        """Prime-Directive claims (§0.4) for filed GSTR-3B interest — the GST figure Mahsa can
        independently reconstruct (``interest_3b`` in ``dif/src/recompute/gst_fees.rs``). Inputs
        (cash_tax = persisted ``tax_payable``, days_late from filed/due dates) are exactly what
        ``file_gstr3b`` computed the interest on, so Mahsa recomputes the identical figure and
        BLOCKs on any mismatch.

        ``late_fee_3b`` is deliberately NOT claimed: its ``is_nil`` flag (nil vs regular return —
        different rate and cap) is a caller-supplied argument that is not persisted on
        ``GstReturn``, and ``tax_payable == 0`` is only a proxy for it (a return can have zero
        cash after full ITC set-off yet not be a NIL return). Rather than emit a claim on a
        guessed input that could falsely BLOCK a correct late fee, the late fee stays
        honest-pending. GSTR-1 / ITC set-off are likewise not single-value recompute targets."""
        claims: list[RecomputeClaim] = []
        returns = session.scalars(
            select(GstReturn).where(GstReturn.return_type == "GSTR-3B")
        ).all()
        for ret in returns:
            if not ret.filed_date:
                continue
            days_late = max(0, _days_between(ret.filed_date, ret.due_date))
            if days_late <= 0:
                continue
            claims.append(
                RecomputeClaim(
                    target="interest_3b",
                    inputs={"cash_tax": int(ret.tax_payable), "days_late": days_late},
                    claimed_paise=int(ret.interest),
                    label=f"gst.return{ret.id}.interest_3b",
                )
            )
        return claims

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        anchor_iso = anchor.isoformat()

        # Latest GSTR-3B filing status -> days late / filing timeliness.
        latest = session.scalars(
            select(GstReturn)
            .where(GstReturn.return_type == "GSTR-3B")
            .order_by(GstReturn.filing_period.desc())
        ).first()
        gstr3b_days_late = 0
        filing_timeliness = 1.0
        if latest is not None:
            if latest.status == "filed" and latest.filed_date:
                gstr3b_days_late = max(0, _days_between(latest.filed_date, latest.due_date))
            elif latest.status != "filed" and anchor_iso > latest.due_date:
                gstr3b_days_late = max(0, _days_between(anchor_iso, latest.due_date))
            filing_timeliness = 0.0 if gstr3b_days_late > 0 else 1.0

        recon = self.reconcile_itc(session)
        ratio = recon["itc_claimed_ratio"]
        # reconciliation health: full when claimed <= available; degrades as the gap grows.
        gap_fraction = max(0.0, ratio - 1.0)
        reconciliation_gap = max(0.0, 1.0 - gap_fraction)

        return {
            "as_of": anchor_iso,
            "metrics": {
                "filing_timeliness": filing_timeliness,
                "itc_optimization": 1.0,
                "e_invoice_readiness": 1.0,
                "hsn_accuracy": 1.0,
                "rcm_compliance": 1.0,
                "lut_validity": 1.0,
                "reconciliation_gap": reconciliation_gap,
                "penalty_exposure": 1.0 if gstr3b_days_late == 0 else 0.0,
                # signals consumed by GST-001 / GST-002 rules
                "gstr3b_days_late": gstr3b_days_late,
                "itc_claimed_ratio": ratio,
            },
        }
