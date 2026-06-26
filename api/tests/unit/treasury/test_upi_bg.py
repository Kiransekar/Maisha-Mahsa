"""UPI reconciliation + bank-guarantee tracking — deferred features."""

from __future__ import annotations

from datetime import date

from app.core.money import Paise
from app.domains.treasury.service import bank_guarantee_status, upi_reconcile


def test_upi_reconcile_matches_and_flags() -> None:
    bank = [{"reference": "UPI1", "amount": Paise.from_rupees(500)},
            {"reference": "UPI2", "amount": Paise.from_rupees(800)}]
    upi = [{"reference": "UPI1", "amount": Paise.from_rupees(500)},
           {"reference": "UPI3", "amount": Paise.from_rupees(900)}]  # not in bank
    res = upi_reconcile(bank, upi)
    assert res["matched"] == ["UPI1"]
    assert res["unmatched_upi"] == ["UPI3"]
    assert res["unmatched_bank"] == ["UPI2"]
    assert res["reconciled"] is False


def test_upi_reconcile_clean() -> None:
    rows = [{"reference": "A", "amount": 100}]
    assert upi_reconcile(rows, rows)["reconciled"] is True


def test_bank_guarantee_status() -> None:
    as_of = date(2026, 6, 24)
    assert bank_guarantee_status("2026-12-31", as_of)["expired"] is False
    assert bank_guarantee_status("2026-01-01", as_of)["expired"] is True
    near = bank_guarantee_status("2026-07-10", as_of)  # 16 days out
    assert near["renewal_due"] is True and near["days_to_expiry"] == 16
