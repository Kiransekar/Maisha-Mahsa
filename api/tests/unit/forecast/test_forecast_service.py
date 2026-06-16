from datetime import date

from app.core.money import Paise
from app.domains.forecast.service import ForecastService


def test_scenario_runway(session):
    svc = ForecastService()
    # ₹12L cash, revenue ₹3L, cost ₹5L -> net −₹2L/mo -> 6 months to zero
    res = svc.scenario(
        opening_cash=Paise.from_rupees(1200000),
        base_revenue=Paise.from_rupees(300000),
        base_cost=Paise.from_rupees(500000),
        horizon_months=12,
    )
    assert res["monthly_net_change"] == Paise.from_rupees(-200000)
    assert res["months_to_zero"] == 6


def test_record_forecast_persists_min_cash(session):
    svc = ForecastService()
    res = svc.record_forecast(
        session,
        forecast_date="2026-06-16",
        opening_cash=Paise.from_rupees(300000),
        monthly_net_change=[Paise.from_rupees(-100000)] * 4,
    )
    assert res["min_cash"] == Paise.from_rupees(-100000)
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["forecast_min_cash_paise"] == Paise.from_rupees(-100000)


def test_build_snapshot_healthy_when_no_forecast(session):
    svc = ForecastService()
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["forecast_min_cash_paise"] == 0  # nothing projected -> healthy
