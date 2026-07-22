"""s.234B interest — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.tax.tax_calc import interest_234b


def test_no_interest_when_90pc_paid() -> None:
    assessed = Paise.from_rupees(100000)
    res = interest_234b(assessed, Paise.from_rupees(95000), months=4)  # 95% >= 90%
    assert res["applicable"] is False
    assert res["interest"] == 0


def test_interest_on_full_shortfall() -> None:
    assessed = Paise.from_rupees(100000)
    res = interest_234b(assessed, 0, months=4)  # nothing paid -> 1%/mo on ₹1,00,000 for 4 mo
    assert res["applicable"] is True
    assert res["shortfall"] == Paise.from_rupees(100000)
    assert res["interest"] == Paise.from_rupees(4000)  # 1,00,000 × 1% × 4


def test_shortfall_rounded_down_to_hundred() -> None:
    # THE ROUNDING MUST BE EXERCISED, NOT INERT: assessed ₹1,00,050, paid ₹0 -> raw shortfall
    # ₹1,00,050 is NOT a ₹100 multiple; Rule 119A(c) rounds the interest base DOWN to ₹1,00,000.
    # (The old input here — paid ₹50 — produced a shortfall already at ₹1,00,000, so deleting
    # the rounding line kept this test green: a vacuous lock, caught by mutation-check.)
    res = interest_234b(Paise.from_rupees(100050), 0, months=1)
    assert res["shortfall"] == Paise.from_rupees(100000)  # 1,00,050 -> 1,00,000
    assert res["interest"] == Paise.from_rupees(1000)

    # Paired: a shortfall already on the ₹100 boundary passes through unchanged.
    res2 = interest_234b(Paise.from_rupees(100050), Paise.from_rupees(50), months=1)
    assert res2["shortfall"] == Paise.from_rupees(100000)
    assert res2["interest"] == Paise.from_rupees(1000)
