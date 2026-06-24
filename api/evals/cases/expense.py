"""Expense eval cases. A ₹5,000 meals claim breaches the ₹2,000 policy; with a ₹10,000 travel
claim, one claim is over-policy and ₹15,000 is pending. Trips EXPENSE-001. Ground truth
mirrors ``tests/unit/expense/test_expense_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.domains.expense.service import ExpenseService
from app.llm.schema import ActionClaim, RuleAssertion

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_claims(session: Session) -> None:
    svc = ExpenseService()
    svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="meals",
        amount=Paise.from_rupees(5000),  # over the ₹2,000 meals cap
    )
    svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="travel",
        amount=Paise.from_rupees(10000),  # within the ₹50,000 travel cap
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="expense-over-policy",
        domain="expense",
        query="Are any expense claims over policy and how much is pending?",
        seed=_seed_claims,
        as_of=_AS_OF,
        expect=Expectation(
            claims={
                "over_policy_claims": "1",
                "pending_reimbursement_paise": "1500000",  # ₹15,000
            },
            citations=["Internal expense policy / EXP-1"],
            expected_status="yellow",
        ),
        stub_claim=ActionClaim(
            domain="expense",
            narrative="One claim (₹5,000 meals) is over policy; ₹15,000 total is pending.",
            claims={"over_policy_claims": "1", "pending_reimbursement_paise": "1500000"},
            rule_assertions=[
                RuleAssertion(
                    rule_id="EXPENSE-001", statute="Internal expense policy", section="EXP-1"
                )
            ],
        ),
    ),
]
