"""Deferred / accrual revenue recognition — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.revenue.revenue_calc import deferred_revenue_schedule

_TOTAL = Paise.from_rupees(120000)  # ₹1,20,000 annual contract


def test_half_way_through_contract() -> None:
    res = deferred_revenue_schedule(_TOTAL, start="2026-01-01", months=12, as_of="2026-07-01")
    assert res["months_elapsed"] == 6
    assert res["monthly"] == Paise.from_rupees(10000)
    assert res["recognized"] == Paise.from_rupees(60000)
    assert res["deferred"] == Paise.from_rupees(60000)


def test_before_start_nothing_recognized() -> None:
    res = deferred_revenue_schedule(_TOTAL, start="2026-06-01", months=12, as_of="2026-01-01")
    assert res["months_elapsed"] == 0
    assert res["recognized"] == 0 and res["deferred"] == _TOTAL


def test_after_end_fully_recognized_no_rounding_leak() -> None:
    # ₹1,00,000 over 3 months -> 33,333.33/mo; final period absorbs rounding to exactly total
    total = Paise.from_rupees(100000)
    res = deferred_revenue_schedule(total, start="2026-01-01", months=3, as_of="2027-01-01")
    assert res["recognized"] == total and res["deferred"] == 0
