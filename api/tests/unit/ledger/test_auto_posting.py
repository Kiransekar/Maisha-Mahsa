"""Auto journal posting from payroll/GST/revenue source events — deferred feature."""

from __future__ import annotations

import pytest

from app.core.money import Paise
from app.db.models.ledger import JournalEntry
from app.domains.ledger import ledger_calc
from app.domains.ledger.service import LedgerService

# ── pure builders ───────────────────────────────────────────────────────────────────

def test_payroll_journal_is_balanced() -> None:
    lines = ledger_calc.payroll_journal(
        salary_expense_account=1, bank_account=2, statutory_payable_account=3,
        gross=Paise.from_rupees(150000), net=Paise.from_rupees(120000),
        statutory=Paise.from_rupees(30000),
    )
    assert ledger_calc.is_balanced(lines)


def test_payroll_journal_rejects_imbalance() -> None:
    with pytest.raises(ValueError):
        ledger_calc.payroll_journal(
            salary_expense_account=1, bank_account=2, statutory_payable_account=3,
            gross=Paise.from_rupees(150000), net=Paise.from_rupees(120000),
            statutory=Paise.from_rupees(10000),  # net + statutory != gross
        )


def test_sales_and_gst_journals_balanced() -> None:
    s = ledger_calc.sales_journal(
        receivable_account=1, sales_account=2, gst_output_account=3,
        taxable=Paise.from_rupees(100000), tax=Paise.from_rupees(18000),
    )
    g = ledger_calc.gst_payment_journal(
        gst_payable_account=3, bank_account=2, amount=Paise.from_rupees(18000)
    )
    assert ledger_calc.is_balanced(s) and ledger_calc.is_balanced(g)


# ── service auto_post ─────────────────────────────────────────────────────────────────

def test_auto_post_payroll_tags_source_and_balances(session) -> None:  # type: ignore[no-untyped-def]
    svc = LedgerService()
    salary = svc.create_account(session, code="5100", name="Salaries", account_type="expense")
    bank = svc.create_account(session, code="1010", name="Bank", account_type="asset", is_bank=True)
    payable = svc.create_account(
        session, code="2100", name="Statutory payable", account_type="liability"
    )

    lines = ledger_calc.payroll_journal(
        salary_expense_account=salary, bank_account=bank, statutory_payable_account=payable,
        gross=Paise.from_rupees(150000), net=Paise.from_rupees(120000),
        statutory=Paise.from_rupees(30000),
    )
    res = svc.auto_post(session, source="payroll", entry_date="2026-06-30",
                        description="June payroll", lines=lines)

    entry = session.get(JournalEntry, res["journal_entry_id"])
    assert entry.source == "payroll" and entry.is_auto_generated == 1
    assert svc.trial_balance(session)["diff"] == 0  # books still tie out
    # net pay left the bank
    assert svc.general_ledger(session, bank)["closing_balance"] == -Paise.from_rupees(120000)


def test_auto_post_rejects_manual_source(session) -> None:  # type: ignore[no-untyped-def]
    svc = LedgerService()
    a = svc.create_account(session, code="1", name="A", account_type="asset")
    b = svc.create_account(session, code="2", name="B", account_type="income")
    lines = [
        {"account_id": a, "debit": 100, "credit": 0},
        {"account_id": b, "debit": 0, "credit": 100},
    ]
    with pytest.raises(ValueError):
        svc.auto_post(
            session, source="manual", entry_date="2026-06-30", description="x", lines=lines
        )
