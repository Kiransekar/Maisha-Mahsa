"""Cash flow statement + bank reconciliation — deferred features."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.ledger.ledger_calc import bank_reconciliation
from app.domains.ledger.service import LedgerService


def test_cash_flow_classifies_by_counterpart(session) -> None:  # type: ignore[no-untyped-def]
    svc = LedgerService()
    cash = svc.create_account(session, code="1000", name="Cash", account_type="asset", is_cash=True)
    capital = svc.create_account(session, code="3000", name="Capital", account_type="equity")
    creditors = svc.create_account(session, code="2000", name="Loan", account_type="liability")
    sales = svc.create_account(session, code="4000", name="Sales", account_type="income")
    rent = svc.create_account(session, code="5000", name="Rent", account_type="expense")

    def je(dr, cr, amt):  # type: ignore[no-untyped-def]
        svc.post_journal_entry(
            session,
            entry_date="2026-05-01",
            description="x",
            lines=[
                {"account_id": dr, "debit": Paise.from_rupees(amt), "credit": 0},
                {"account_id": cr, "debit": 0, "credit": Paise.from_rupees(amt)},
            ],
        )

    je(cash, capital, 3000)  # financing
    je(cash, creditors, 2000)  # financing
    je(cash, sales, 4000)  # operating
    je(rent, cash, 1000)  # operating (cash out)

    cf = svc.cash_flow(session)
    assert cf["operating"] == Paise.from_rupees(3000)  # 4,000 − 1,000
    assert cf["financing"] == Paise.from_rupees(5000)  # 3,000 + 2,000
    assert cf["investing"] == 0
    assert cf["net_change"] == Paise.from_rupees(8000)


def test_cash_flow_zero_without_flagged_cash(session) -> None:  # type: ignore[no-untyped-def]
    LedgerService().create_account(session, code="1000", name="Cash", account_type="asset")
    assert LedgerService().cash_flow(session)["net_change"] == 0  # no cash account flagged


def test_bank_reconciliation() -> None:
    rec = bank_reconciliation(
        Paise.from_rupees(10000),
        Paise.from_rupees(12000),
        unpresented_cheques=Paise.from_rupees(2000),
    )
    assert rec["adjusted_bank_balance"] == Paise.from_rupees(10000)
    assert rec["difference"] == 0 and rec["reconciled"] is True


def test_bank_reconciliation_mismatch() -> None:
    rec = bank_reconciliation(Paise.from_rupees(10000), Paise.from_rupees(9000))
    assert rec["difference"] == Paise.from_rupees(1000)
    assert rec["reconciled"] is False
