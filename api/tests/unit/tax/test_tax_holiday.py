"""s.80-IAC tax holiday — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.tax.tax_calc import tax_holiday_deduction

_PROFIT = Paise.from_rupees(5000000)


def test_eligible_first_year_full_deduction() -> None:
    res = tax_holiday_deduction(_PROFIT, claimed_years=0, eligible=True)
    assert res["eligible"] is True
    assert res["deduction"] == _PROFIT
    assert res["taxable_after_holiday"] == 0
    assert res["holiday_years_remaining"] == 2


def test_exhausted_after_three_years() -> None:
    res = tax_holiday_deduction(_PROFIT, claimed_years=3, eligible=True)
    assert res["eligible"] is False
    assert res["deduction"] == 0
    assert res["taxable_after_holiday"] == _PROFIT


def test_not_eligible_or_loss() -> None:
    assert tax_holiday_deduction(_PROFIT, claimed_years=0, eligible=False)["deduction"] == 0
    assert tax_holiday_deduction(-100, claimed_years=0, eligible=True)["deduction"] == 0
