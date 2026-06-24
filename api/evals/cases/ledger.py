"""Ledger eval cases. A small balanced set of books: trial balance nets to zero and net
profit is ₹3,000. Ground truth mirrors ``tests/unit/ledger/test_ledger_service.py``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.domains.ledger.service import LedgerService
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation


def _seed_books(session: Session) -> None:
    svc = LedgerService()
    ids = {
        "cash": svc.create_account(session, code="1000", name="Cash", account_type="asset"),
        "capital": svc.create_account(session, code="3000", name="Capital", account_type="equity"),
        "creditors": svc.create_account(
            session, code="2000", name="Creditors", account_type="liability"
        ),
        "sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
        "rent": svc.create_account(session, code="5000", name="Rent", account_type="expense"),
    }

    def je(desc: str, dr: str, cr: str, amt: int) -> None:
        svc.post_journal_entry(
            session,
            entry_date="2026-05-01",
            description=desc,
            lines=[
                {"account_id": ids[dr], "debit": Paise.from_rupees(amt), "credit": 0},
                {"account_id": ids[cr], "debit": 0, "credit": Paise.from_rupees(amt)},
            ],
        )

    je("capital introduced", "cash", "capital", 3000)
    je("loan taken", "cash", "creditors", 2000)
    je("cash sale", "cash", "sales", 4000)
    je("paid rent", "rent", "cash", 1000)


CASES: list[EvalCase] = [
    EvalCase(
        id="ledger-balanced-books",
        domain="ledger",
        query="Do the books balance and what's the net profit?",
        seed=_seed_books,
        expect=Expectation(
            claims={
                "trial_balance_diff_paise": "0",  # balanced
                "net_profit_paise": "300000",  # ₹3,000 (sales 4,000 − rent 1,000)
            },
        ),
        stub_claim=ActionClaim(
            domain="ledger",
            narrative="Trial balance is zero; net profit is ₹3,000 (₹4,000 sales − ₹1,000 rent).",
            claims={"trial_balance_diff_paise": "0", "net_profit_paise": "300000"},
        ),
    ),
]
