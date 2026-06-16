"""Expense service: claim submission with policy check, approval/reimbursement workflow,
receipt parsing, category analytics, and the expense health snapshot for Mahsa.

Expense has no Mahsa sub-vector; Mahsa enforces EXPENSE-001 (no over-policy claims pending
approval) on the snapshot's ``over_policy_claims``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.expense import ExpenseClaim
from app.domains.expense import expense_calc
from app.domains.expense.manifest import MANIFEST


class ExpenseService(BaseDomainService):
    domain = "expense"
    keywords = (
        "expense",
        "reimbursement",
        "petty cash",
        "claim",
        "mileage",
        "receipt",
        "per diem",
        "conveyance",
    )
    manifest = MANIFEST

    # ---- claims ---------------------------------------------------------------------

    def submit_claim(
        self,
        session: Session,
        *,
        claim_date: str,
        expense_date: str,
        category: str,
        amount: int,
        gst_amount: int = 0,
        employee_id: int | None = None,
        vendor_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        policy = expense_calc.check_policy(category, amount)
        claim = ExpenseClaim(
            employee_id=employee_id,
            claim_date=claim_date,
            expense_date=expense_date,
            category=category,
            amount=amount,
            gst_amount=gst_amount,
            vendor_name=vendor_name,
            description=description,
            over_policy=1 if policy["over_policy"] else 0,
            status="submitted",
        )
        session.add(claim)
        session.flush()
        return {
            "claim_id": claim.id,
            "amount": amount,
            "over_policy": policy["over_policy"],
            "policy_limit": policy["limit"],
            "excess": policy["excess"],
            "petty_cash_eligible": expense_calc.is_petty_cash_eligible(amount),
        }

    def approve_claim(
        self, session: Session, claim_id: int, *, approver: str, approved_date: str
    ) -> None:
        claim = session.get(ExpenseClaim, claim_id)
        if claim is None:
            raise ValueError(f"expense claim {claim_id} not found")
        claim.status = "approved"
        claim.approved_by = approver
        claim.approved_date = approved_date
        session.flush()

    def mark_reimbursed(self, session: Session, claim_id: int, *, reimbursement_date: str) -> None:
        claim = session.get(ExpenseClaim, claim_id)
        if claim is None:
            raise ValueError(f"expense claim {claim_id} not found")
        claim.status = "reimbursed"
        claim.reimbursement_date = reimbursement_date
        session.flush()

    def category_spend(self, session: Session) -> dict[str, int]:
        claims = [
            {"category": c.category, "amount": int(c.amount)}
            for c in session.scalars(select(ExpenseClaim)).all()
        ]
        return expense_calc.category_spend(claims)

    def parse_receipt(self, ocr_text: str) -> dict[str, Any]:
        return expense_calc.parse_receipt(ocr_text)

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        open_claims = [
            c for c in session.scalars(select(ExpenseClaim)).all() if c.status != "rejected"
        ]
        over_policy = sum(1 for c in open_claims if c.over_policy)
        pending = sum(int(c.amount) for c in open_claims if c.status in ("submitted", "approved"))
        return {
            "as_of": anchor.isoformat(),
            "metrics": {
                # consumed by EXPENSE-001
                "over_policy_claims": over_policy,
                "pending_reimbursement_paise": pending,
            },
        }
