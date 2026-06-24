"""Convertible-note interest accrual — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.equity.equity_calc import convertible_note_value


def test_simple_interest() -> None:
    res = convertible_note_value(Paise.from_rupees(5000000), annual_rate=0.08, months=12)
    assert res["interest"] == Paise.from_rupees(400000)  # 50,00,000 × 8% × 1yr
    assert res["maturity_value"] == Paise.from_rupees(5400000)


def test_monthly_compounding_exceeds_simple() -> None:
    simple = convertible_note_value(
        Paise.from_rupees(5000000), annual_rate=0.08, months=12, compounding="simple"
    )
    compound = convertible_note_value(
        Paise.from_rupees(5000000), annual_rate=0.08, months=12, compounding="monthly"
    )
    assert compound["interest"] > simple["interest"]  # compounding accrues more
    assert compound["maturity_value"] == Paise.from_rupees(5000000) + compound["interest"]


def test_zero_months_no_interest() -> None:
    res = convertible_note_value(Paise.from_rupees(1000000), annual_rate=0.1, months=0)
    assert res["interest"] == 0
