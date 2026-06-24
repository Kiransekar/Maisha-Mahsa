"""Quarterly rolling re-forecast — deferred feature."""

from __future__ import annotations

from app.domains.forecast.forecast_calc import rolling_reforecast


def test_blends_actuals_with_remaining_budget() -> None:
    budget = [100, 100, 100, 100]
    actuals = [120, 90]  # two periods actualised
    res = rolling_reforecast(actuals, budget)
    assert res["reforecast"] == [120, 90, 100, 100]
    assert res["periods_actualised"] == 2
    assert res["reforecast_total"] == 410
    assert res["original_total"] == 400
    assert res["variance"] == 10


def test_no_actuals_matches_budget() -> None:
    res = rolling_reforecast([], [50, 50, 50])
    assert res["reforecast"] == [50, 50, 50]
    assert res["variance"] == 0
