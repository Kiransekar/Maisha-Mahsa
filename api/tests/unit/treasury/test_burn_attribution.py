"""Burn attribution by category — deferred feature."""

from __future__ import annotations

from datetime import date

from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.domains.treasury.service import TreasuryService


def _seed(session):  # type: ignore[no-untyped-def]
    acct = BankAccount(bank_name="HDFC", account_number="1", ifsc="HDFC0000001")
    session.add(acct)
    session.flush()
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-15",
                                debit=Paise.from_rupees(9000), credit=0, category="cloud"))
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-20",
                                debit=Paise.from_rupees(5000), credit=0, category="salary"))
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-21",
                                debit=Paise.from_rupees(1000), credit=0))  # uncategorised
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-22",
                                debit=0, credit=Paise.from_rupees(7000)))  # credit -> ignored
    session.flush()


def test_burn_grouped_by_category(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    res = TreasuryService().burn_attribution(session, date(2026, 6, 30), months=3)
    assert res["total_debits_paise"] == Paise.from_rupees(15000)  # 9k + 5k + 1k
    assert res["by_category"]["cloud"] == Paise.from_rupees(9000)
    assert res["by_category"]["salary"] == Paise.from_rupees(5000)
    assert res["by_category"]["uncategorised"] == Paise.from_rupees(1000)
    # sorted descending by spend
    assert list(res["by_category"])[0] == "cloud"
