"""Budgeting & forecasting core — pure, deterministic. Money is integer paise; ratios are
floats. Covers budget variance, rolling cash projection (with overdraft detection), scenario
net-burn, the burn multiple, and SaaS unit economics (CAC / LTV / payback).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _year_month_index(year_month: str) -> int:
    """'YYYY-MM' -> absolute month index for arithmetic."""
    year, month = year_month.split("-")
    return int(year) * 12 + (int(month) - 1)


def revenue_recognition_forecast(
    contracts: list[dict], *, horizon_months: int, start: str
) -> dict[str, Any]:
    """Straight-line (ratable) revenue-recognition forecast per Ind AS 115. Each contract:
    {total_paise, start 'YYYY-MM', term_months} — its value is recognised evenly over the
    term (rounding remainder into the final month). Returns recognised revenue per month for
    ``horizon_months`` from ``start`` ('YYYY-MM'). Pure & deterministic."""
    start_idx = _year_month_index(start)
    monthly = [0] * max(0, int(horizon_months))
    for c in contracts:
        total = int(c["total_paise"])
        term = max(1, int(c["term_months"]))
        c_start = _year_month_index(c["start"])
        per_month = total // term
        remainder = total - per_month * term  # trued up in the last month
        for k in range(term):
            idx = c_start + k - start_idx
            if 0 <= idx < len(monthly):
                monthly[idx] += per_month + (remainder if k == term - 1 else 0)
    return {
        "start": start,
        "horizon_months": int(horizon_months),
        "monthly": monthly,
        "total_recognized": sum(monthly),
    }


def variance(actual: int, budget: int) -> dict[str, Any]:
    """Actual vs budget. Positive amount = over budget (spent more than planned)."""
    amount = int(actual) - int(budget)
    pct = round(amount / int(budget) * 100, 2) if budget else 0.0
    return {"amount": amount, "pct": pct, "over_budget": amount > 0}


def project_cash(opening_cash: int, monthly_net_change: list[int]) -> dict[str, Any]:
    """Roll an opening balance forward by monthly net changes (signed paise; burn is
    negative). Returns month-end balances, the minimum balance over the horizon, and the
    number of whole months survived before cash first turns negative (None if it never does)."""
    balances: list[int] = []
    bal = int(opening_cash)
    months_to_zero: int | None = None
    for i, change in enumerate(monthly_net_change):
        bal += int(change)
        balances.append(bal)
        if months_to_zero is None and bal < 0:
            months_to_zero = i
    min_cash = min(balances) if balances else int(opening_cash)
    return {"balances": balances, "min_cash": min_cash, "months_to_zero": months_to_zero}


def scenario_net_change(
    base_revenue: int, base_cost: int, *, revenue_mult: float = 1.0, extra_cost: int = 0
) -> int:
    """Monthly net change for a scenario: revenue×mult − (cost + extra). Negative = burn."""
    revenue = int(
        (Decimal(int(base_revenue)) * Decimal(str(revenue_mult))).to_integral_value(ROUND_HALF_UP)
    )
    return revenue - (int(base_cost) + int(extra_cost))


def runway_months(cash: int, monthly_net_burn: int) -> float | None:
    """Months of runway at a constant net burn. None when not burning."""
    if int(monthly_net_burn) <= 0:
        return None
    return round(int(cash) / int(monthly_net_burn), 2)


def burn_multiple(net_burn: int, net_new_arr: int) -> float | None:
    """Net burn / net new ARR (lower is better). None when there is no new ARR."""
    if int(net_new_arr) <= 0:
        return None
    return round(int(net_burn) / int(net_new_arr), 2)


def unit_economics(
    *,
    sales_marketing_spend: int,
    new_customers: int,
    arpu: int,
    gross_margin: float,
    lifetime_months: int,
) -> dict[str, Any]:
    """CAC, LTV, payback and the LTV:CAC ratio. ``arpu`` is monthly revenue per account
    (paise); ``gross_margin`` is a fraction (e.g. 0.80)."""
    if new_customers <= 0:
        raise ValueError("new_customers must be positive")
    cac = int(sales_marketing_spend) // int(new_customers)
    contribution = Decimal(int(arpu)) * Decimal(str(gross_margin))  # monthly gross profit/account
    ltv = int(contribution * int(lifetime_months))
    payback_months = round(float(Decimal(cac) / contribution), 2) if contribution > 0 else None
    ltv_cac = round(ltv / cac, 2) if cac > 0 else None
    return {"cac": cac, "ltv": ltv, "payback_months": payback_months, "ltv_cac_ratio": ltv_cac}


def rolling_reforecast(actuals: list[int], budget: list[int]) -> dict[str, Any]:
    """Quarterly re-forecast: replace the elapsed periods of the budget with actuals and keep
    the original budget for the remaining periods. Returns the blended series and the variance
    against the original plan."""
    elapsed = len(actuals)
    reforecast = list(actuals) + list(budget[elapsed:])
    reforecast_total = sum(int(x) for x in reforecast)
    original_total = sum(int(x) for x in budget)
    return {
        "reforecast": reforecast,
        "reforecast_total": reforecast_total,
        "original_total": original_total,
        "variance": reforecast_total - original_total,
        "periods_actualised": elapsed,
    }


def headcount_forecast(roles: list[dict], *, months: int) -> dict[str, Any]:
    """Headcount plan → payroll cost forecast. Each role: {count, monthly_cost} (paise,
    fully-loaded). Returns total headcount, monthly + annualised cost, and a flat projection."""
    headcount = sum(int(r["count"]) for r in roles)
    monthly_cost = sum(int(r["count"]) * int(r["monthly_cost"]) for r in roles)
    return {
        "headcount": headcount,
        "monthly_cost": monthly_cost,
        "annualised_cost": monthly_cost * 12,
        "projection": [monthly_cost] * max(0, months),
    }
