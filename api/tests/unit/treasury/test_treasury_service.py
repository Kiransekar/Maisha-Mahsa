from datetime import date

from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.domains.treasury.service import TreasuryService, _months_back

CANONICAL = """date,description,reference,debit,credit,balance
2026-05-05,Opening,REF1,0,100000,100000
2026-05-10,AWS invoice,REF2,20000,0,80000
2026-06-01,Customer payment,REF3,0,50000,130000
2026-06-12,Salary,REF4,40000,0,90000
"""

# HDFC-style headers and dd/mm/yyyy dates, amounts with commas.
HDFC = """Date,Narration,Chq./Ref.No.,Withdrawal Amt.,Deposit Amt.,Closing Balance
05/05/2026,OPENING,REF1,0.00,"1,00,000.00","1,00,000.00"
10/05/2026,AWS,REF2,"20,000.00",0.00,"80,000.00"
"""


def _account(session, balance_paise=0):
    acct = BankAccount(
        bank_name="HDFC",
        account_number="0001",
        ifsc="HDFC0000001",
        opening_balance=balance_paise,
        current_balance=balance_paise,
    )
    session.add(acct)
    session.flush()
    return acct


def test_import_canonical_csv(session):
    svc = TreasuryService()
    acct = _account(session)
    result = svc.import_csv(session, acct.id, CANONICAL)
    assert result["rows_imported"] == 4
    assert result["rows_skipped"] == 0
    # closing balance follows the statement's balance column (₹90,000)
    assert result["closing_balance_paise"] == Paise.from_rupees(90000)
    assert acct.current_balance == Paise.from_rupees(90000)


def test_import_hdfc_format_with_commas(session):
    svc = TreasuryService()
    acct = _account(session)
    result = svc.import_csv(session, acct.id, HDFC)
    assert result["rows_imported"] == 2
    assert result["closing_balance_paise"] == Paise.from_rupees(80000)


def test_unrecognised_csv_raises(session):
    svc = TreasuryService()
    acct = _account(session)
    try:
        svc.import_csv(session, acct.id, "foo,bar\n1,2\n")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_cash_position_aggregates_accounts(session):
    svc = TreasuryService()
    a = _account(session, Paise.from_rupees(900000))
    b = BankAccount(
        bank_name="ICICI",
        account_number="2",
        ifsc="ICIC0000002",
        current_balance=Paise.from_rupees(100000),
    )
    session.add(b)
    session.flush()
    pos = svc.cash_position(session)
    assert pos["total_cash_paise"] == Paise.from_rupees(1000000)
    assert pos["account_count"] == 2
    assert pos["largest_account_share"] == 0.9
    _ = a  # used via session


def test_metrics_runway_is_exact(session):
    svc = TreasuryService()
    acct = _account(session, Paise.from_rupees(1200000))  # ₹12,00,000 cash
    # one ₹6,00,000 outflow inside the trailing 3-month window
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-05-10",
            debit=Paise.from_rupees(600000),
            credit=0,
        )
    )
    session.flush()
    m = svc.metrics(session, date(2026, 6, 16), months=3)
    assert m["monthly_burn_paise"] == Paise.from_rupees(200000)  # 6L / 3
    assert m["monthly_revenue_paise"] == 0
    assert m["net_burn_paise"] == Paise.from_rupees(200000)
    assert m["runway_months"] == 6.0  # 12L / 2L


def test_metrics_no_burn_means_infinite_runway(session):
    svc = TreasuryService()
    acct = _account(session, Paise.from_rupees(500000))
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-06-01",
            debit=0,
            credit=Paise.from_rupees(100000),
        )
    )
    session.flush()
    m = svc.metrics(session, date(2026, 6, 16))
    assert m["runway_months"] is None


def test_build_snapshot_shape(session):
    svc = TreasuryService()
    _account(session, Paise.from_rupees(1000000))
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert set(snap) >= {
        "as_of",
        "cash",
        "monthly_burn",
        "monthly_revenue",
        "bank_account_count",
        "largest_account_share",
    }
    assert snap["cash"] == Paise.from_rupees(1000000)


def test_months_back_clamps_day():
    # 31 May minus 3 months -> end of Feb (clamped)
    assert _months_back(date(2026, 5, 31), 3) == date(2026, 2, 28)
