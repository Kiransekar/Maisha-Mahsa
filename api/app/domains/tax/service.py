"""Tax service: advance tax + s.234C, TDS returns + s.234E, TDS aggregation from payroll
and payables, and the tax health snapshot for Mahsa. Exact paise; deterministic."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.payables import Bill
from app.db.models.payroll import PayrollEntry, PayrollRun
from app.db.models.tax import AdvanceTax, TdsEntry, TdsReturn
from app.domains.tax import tax_calc
from app.domains.tax.manifest import MANIFEST


def _tds_due_date(payment_date: str) -> date:
    """TDS deposit due date: the 7th of the month following the payment month."""
    d = date.fromisoformat(payment_date)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, 7)


class TaxService(BaseDomainService):
    domain = "tax"
    keywords = (
        "advance tax",
        "tds return",
        "income tax",
        "itr",
        "26as",
        "mat",
        "234c",
        "234e",
        "44ab",
        "tax audit",
    )
    manifest = MANIFEST

    # ---- TDS returns ----------------------------------------------------------------

    def file_tds_return(
        self,
        session: Session,
        *,
        return_type: str,
        quarter: str,
        due_date: str,
        total_deducted: int,
        filed_date: str | None = None,
    ) -> dict[str, Any]:
        days_late = 0
        if filed_date:
            days_late = max(0, (date.fromisoformat(filed_date) - date.fromisoformat(due_date)).days)
        late_fee = tax_calc.late_fee_234e(days_late, total_deducted)
        ret = TdsReturn(
            return_type=return_type,
            quarter=quarter,
            due_date=due_date,
            filed_date=filed_date,
            status="filed" if filed_date else "pending",
            total_deducted=total_deducted,
            late_filing_fee=late_fee,
        )
        session.add(ret)
        session.flush()
        return {
            "tds_return_id": ret.id,
            "return_type": return_type,
            "quarter": quarter,
            "total_deducted": total_deducted,
            "late_filing_fee": late_fee,
            "status": ret.status,
        }

    # ---- TDS aggregation bridge (payroll + payables) --------------------------------

    def tds_deducted_summary(self, session: Session, month: str) -> dict[str, int]:
        """Aggregate TDS deducted in a month ("YYYY-MM") from payroll (s.192) and payables
        (194x) — what tax must deposit/return. Closes the loop with those modules."""
        payroll_tds = 0
        runs = session.scalars(select(PayrollRun).where(PayrollRun.month_year == month)).all()
        run_ids = {r.id for r in runs}
        if run_ids:
            for e in session.scalars(select(PayrollEntry)).all():
                if e.payroll_run_id in run_ids:
                    payroll_tds += int(e.tds)

        payables_tds = sum(
            int(b.tds_amount)
            for b in session.scalars(select(Bill)).all()
            if b.bill_date.startswith(month)
        )
        return {
            "payroll_tds": payroll_tds,
            "payables_tds": payables_tds,
            "total": payroll_tds + payables_tds,
        }

    # ---- advance tax ----------------------------------------------------------------

    def record_advance_tax(
        self,
        session: Session,
        *,
        fy: str,
        installment: str,
        due_date: str,
        amount: int,
        paid_date: str | None = None,
    ) -> int:
        row = AdvanceTax(
            fy=fy,
            installment=installment,
            due_date=due_date,
            amount=amount,
            paid_date=paid_date,
            status="paid" if paid_date else "pending",
        )
        session.add(row)
        session.flush()
        return row.id

    def advance_tax_interest(
        self, session: Session, *, fy: str, total_liability: int
    ) -> dict[str, Any]:
        order = ["Q1", "Q2", "Q3", "Q4"]
        paid_by_installment = dict.fromkeys(order, 0)
        for row in session.scalars(select(AdvanceTax).where(AdvanceTax.fy == fy)).all():
            if row.paid_date and row.installment in paid_by_installment:
                paid_by_installment[row.installment] += int(row.amount)
        cumulative = []
        running = 0
        for q in order:
            running += paid_by_installment[q]
            cumulative.append(running)
        return tax_calc.interest_234c(total_liability, cumulative)

    # ---- Mahsa contract -------------------------------------------------------------

    def _tds_days_overdue(self, session: Session, as_of: date) -> int:
        worst = 0
        for e in session.scalars(select(TdsEntry)).all():
            if e.deposit_date:
                continue
            due = _tds_due_date(e.payment_date)
            if as_of > due:
                worst = max(worst, (as_of - due).days)
        return worst

    def _tds_return_days_late(self, session: Session, as_of: date) -> int:
        worst = 0
        for r in session.scalars(select(TdsReturn)).all():
            due = date.fromisoformat(r.due_date)
            if r.status == "filed" and r.filed_date:
                late = (date.fromisoformat(r.filed_date) - due).days
            elif r.status != "filed" and as_of > due:
                late = (as_of - due).days
            else:
                late = 0
            worst = max(worst, late)
        return worst

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        tds_days_overdue = self._tds_days_overdue(session, anchor)
        tds_return_days_late = self._tds_return_days_late(session, anchor)

        return {
            "as_of": anchor.isoformat(),
            "metrics": {
                "advance_tax_coverage": 1.0,
                "tds_deposit_timeliness": 1.0 if tds_days_overdue == 0 else 0.0,
                "as26_match": 1.0,
                "audit_trigger": 1.0,
                "mat_exposure": 1.0,
                "holiday_utilization": 1.0,
                "tp_documentation": 1.0,
                "itr_accuracy": 1.0,
                # signals for TAX-002 / TAX-003 (TAX-001 needs an estimate; default healthy)
                "tds_days_overdue": tds_days_overdue,
                "tds_return_days_late": tds_return_days_late,
                "advance_tax_q1_ratio": 1.0,
            },
        }
