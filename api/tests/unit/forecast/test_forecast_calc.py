"""Budgeting & forecasting checks — variance, cash projection, scenarios, burn multiple,
unit economics."""

from app.core.money import Paise
from app.domains.forecast import forecast_calc as f


def test_variance():
    v = f.variance(Paise.from_rupees(120000), Paise.from_rupees(100000))
    assert v["amount"] == Paise.from_rupees(20000)
    assert v["pct"] == 20.0
    assert v["over_budget"] is True


def test_project_cash_detects_overdraft():
    # ₹3,00,000 opening, −₹1,00,000/mo for 4 months: 2L, 1L, 0, −1L -> negative at month 3
    proj = f.project_cash(Paise.from_rupees(300000), [Paise.from_rupees(-100000)] * 4)
    assert proj["balances"][2] == 0
    assert proj["balances"][3] == Paise.from_rupees(-100000)
    assert proj["min_cash"] == Paise.from_rupees(-100000)
    assert proj["months_to_zero"] == 3  # survived 3 whole months


def test_project_cash_never_negative():
    proj = f.project_cash(Paise.from_rupees(100000), [Paise.from_rupees(10000)] * 6)
    assert proj["months_to_zero"] is None
    assert proj["min_cash"] == Paise.from_rupees(110000)  # first month-end


def test_scenario_net_change():
    # revenue ₹5L ×1.2 − (cost ₹8L + extra ₹1L) = 6L − 9L = −3L burn
    net = f.scenario_net_change(
        Paise.from_rupees(500000),
        Paise.from_rupees(800000),
        revenue_mult=1.2,
        extra_cost=Paise.from_rupees(100000),
    )
    assert net == Paise.from_rupees(-300000)


def test_burn_multiple():
    assert f.burn_multiple(Paise.from_rupees(800000), Paise.from_rupees(400000)) == 2.0
    assert f.burn_multiple(Paise.from_rupees(800000), 0) is None


def test_unit_economics():
    # CAC = ₹10L / 100 = ₹10,000 ; LTV = ₹2,000 × 0.8 × 24 = ₹38,400
    # payback = 10000 / (2000×0.8=1600) = 6.25 ; LTV:CAC = 38400/10000 = 3.84
    ue = f.unit_economics(
        sales_marketing_spend=Paise.from_rupees(1000000),
        new_customers=100,
        arpu=Paise.from_rupees(2000),
        gross_margin=0.8,
        lifetime_months=24,
    )
    assert ue["cac"] == Paise.from_rupees(10000)
    assert ue["ltv"] == Paise.from_rupees(38400)
    assert ue["payback_months"] == 6.25
    assert ue["ltv_cac_ratio"] == 3.84
