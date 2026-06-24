"""Headcount planning → payroll forecast — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.forecast.forecast_calc import headcount_forecast


def test_headcount_cost_rollup() -> None:
    roles = [
        {"count": 2, "monthly_cost": Paise.from_rupees(150000)},
        {"count": 1, "monthly_cost": Paise.from_rupees(80000)},
    ]
    res = headcount_forecast(roles, months=6)
    assert res["headcount"] == 3
    assert res["monthly_cost"] == Paise.from_rupees(380000)  # 2×1,50,000 + 80,000
    assert res["annualised_cost"] == Paise.from_rupees(380000) * 12
    assert res["projection"] == [Paise.from_rupees(380000)] * 6


def test_empty_plan() -> None:
    res = headcount_forecast([], months=3)
    assert res["headcount"] == 0 and res["monthly_cost"] == 0
    assert res["projection"] == [0, 0, 0]
