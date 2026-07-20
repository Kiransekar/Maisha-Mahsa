"""WS9.2 — bank CSV parsers: SBI, Kotak, Yes, IndusInd, IDFC, Federal, RBL.

These banks emit statement CSVs with different header vocabularies (Narration vs
Particulars vs Description, Txn Date vs Tran Date vs Date, Withdrawal Amt vs Debit
Amount, ...). ``TreasuryService.import_csv`` already normalises "any recognised Indian
bank CSV" into the same shape via header substring matching (see the HDFC/canonical
cases in ``test_treasury_service.py``); this file proves that coverage extends to the
seven banks above using one small representative fixture per bank, and asserts the
resulting rows land in the SAME normalized transaction shape: ISO date, description,
debit/credit paise, balance paise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.domains.treasury.service import TreasuryService

FIXTURES = Path(__file__).parent / "fixtures"


def _account(session, bank_name: str) -> BankAccount:
    acct = BankAccount(
        bank_name=bank_name,
        account_number="TEST0001",
        ifsc="TEST0000001",
        opening_balance=0,
        current_balance=0,
    )
    session.add(acct)
    session.flush()
    return acct


def _rows(session, account_id: int) -> list[BankTransaction]:
    return list(
        session.scalars(
            select(BankTransaction)
            .where(BankTransaction.account_id == account_id)
            .order_by(BankTransaction.id)
        )
    )


def test_sbi_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "SBI")
    result = svc.import_csv(session, acct.id, (FIXTURES / "sbi.csv").read_text())

    assert result["rows_imported"] == 3
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("97550.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-01", "2026-06-05", "2026-06-10"]
    assert rows[0].description == "UPI/1234567890/Zomato"
    assert rows[0].reference == "UPI2606011234"
    assert rows[0].debit == Paise.from_rupees("450.00")
    assert rows[0].credit == 0
    assert rows[0].balance == Paise.from_rupees("49550.00")
    assert rows[1].credit == Paise.from_rupees("50000.00")


def test_kotak_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "Kotak")
    result = svc.import_csv(session, acct.id, (FIXTURES / "kotak.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("200679.50")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-10", "2026-06-15"]
    assert rows[0].description == "UPI/9988776655/Swiggy"
    assert rows[0].debit == Paise.from_rupees("320.50")
    assert rows[1].credit == Paise.from_rupees("75000.00")
    assert rows[1].balance == Paise.from_rupees("200679.50")


def test_yes_bank_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "Yes Bank")
    result = svc.import_csv(session, acct.id, (FIXTURES / "yes.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("145000.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-02", "2026-06-07"]
    assert rows[0].debit == Paise.from_rupees("15000.00")
    assert rows[1].description == "Customer Receipt INV-102"
    assert rows[1].credit == Paise.from_rupees("60000.00")


def test_indusind_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "IndusInd")
    result = svc.import_csv(session, acct.id, (FIXTURES / "indusind.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("175150.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-01", "2026-06-20"]
    assert rows[0].description == "UPI-Rent Payment"
    assert rows[0].debit == Paise.from_rupees("25000.00")
    assert rows[1].credit == Paise.from_rupees("150.00")


def test_idfc_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "IDFC FIRST")
    result = svc.import_csv(session, acct.id, (FIXTURES / "idfc.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("101600.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-03", "2026-06-18"]
    assert rows[0].description == "POS Purchase Office Supplies"
    assert rows[0].debit == Paise.from_rupees("3400.00")
    assert rows[1].credit == Paise.from_rupees("55000.00")


def test_federal_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "Federal Bank")
    result = svc.import_csv(session, acct.id, (FIXTURES / "federal.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("86500.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-05", "2026-06-22"]
    assert rows[0].description == "GST Payment"
    assert rows[0].debit == Paise.from_rupees("18000.00")
    assert rows[1].credit == Paise.from_rupees("4500.00")


def test_rbl_csv_parses_to_normalized_shape(session):
    svc = TreasuryService()
    acct = _account(session, "RBL Bank")
    result = svc.import_csv(session, acct.id, (FIXTURES / "rbl.csv").read_text())

    assert result["rows_imported"] == 2
    assert result["rows_skipped"] == 0
    assert result["closing_balance_paise"] == Paise.from_rupees("152500.00")

    rows = _rows(session, acct.id)
    assert [r.txn_date for r in rows] == ["2026-06-09", "2026-06-25"]
    assert rows[0].description == "NEFT OUT VENDOR PAYMENT"
    assert rows[0].reference == "NEFT001122"
    assert rows[0].debit == Paise.from_rupees("12500.00")
    assert rows[1].credit == Paise.from_rupees("65000.00")
    assert rows[1].balance == Paise.from_rupees("152500.00")


@pytest.mark.parametrize(
    "fixture",
    ["sbi.csv", "kotak.csv", "yes.csv", "indusind.csv", "idfc.csv", "federal.csv", "rbl.csv"],
)
def test_every_bank_fixture_emits_the_same_normalized_fields(session, fixture):
    """Cross-bank contract check: whichever bank the CSV came from, every imported
    transaction exposes the same normalized shape (ISO date, description, debit/credit,
    balance as integer paise) — same as the existing HDFC/canonical parsers."""
    svc = TreasuryService()
    acct = _account(session, fixture)
    result = svc.import_csv(session, acct.id, (FIXTURES / fixture).read_text())
    assert result["rows_imported"] > 0

    for row in _rows(session, acct.id):
        # ISO date (YYYY-MM-DD), not the source format.
        assert len(row.txn_date) == 10 and row.txn_date[4] == "-" and row.txn_date[7] == "-"
        assert isinstance(row.debit, int)
        assert isinstance(row.credit, int)
        assert isinstance(row.balance, int)
        assert row.debit >= 0
        assert row.credit >= 0
