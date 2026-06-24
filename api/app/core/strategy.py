"""F5 — the CFO strategy layer: what-if scenarios on runway, the cap table, and the quarterly
investor update. Deterministic reads over the domain services (no Mahsa, no LLM) so the CFO
panel renders anywhere; money is exact paise throughout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.email.compose import compose_investor_update
from app.core.overview import collect_kpis
from app.domains.equity.service import EquityService
from app.domains.forecast import forecast_calc
from app.domains.treasury.service import TreasuryService


@dataclass(frozen=True)
class Scenario:
    revenue_mult: float
    extra_cost_paise: int
    monthly_net_change_paise: int  # signed; negative = burn
    min_cash_paise: int
    runway_months: float | None  # None when not burning under the scenario


def run_scenario(
    session: Session,
    as_of: date,
    *,
    revenue_mult: float = 1.0,
    extra_cost_paise: int = 0,
    horizon_months: int = 12,
) -> Scenario:
    """Project runway under a revenue multiplier + extra monthly cost, off current treasury
    metrics. revenue_mult=1.0, extra=0 is the base case."""
    tm = TreasuryService().metrics(session, as_of)
    cash = int(tm["cash_paise"])
    net = forecast_calc.scenario_net_change(
        int(tm["monthly_revenue_paise"]),
        int(tm["monthly_burn_paise"]),
        revenue_mult=revenue_mult,
        extra_cost=extra_cost_paise,
    )
    projection = forecast_calc.project_cash(cash, [net] * horizon_months)
    runway = forecast_calc.runway_months(cash, -net) if net < 0 else None
    return Scenario(
        revenue_mult=revenue_mult,
        extra_cost_paise=extra_cost_paise,
        monthly_net_change_paise=net,
        min_cash_paise=int(projection["min_cash"]),
        runway_months=runway,
    )


def cap_table(session: Session) -> dict[str, Any]:
    return EquityService().cap_table(session)


def investor_update(session: Session, as_of: date) -> dict[str, Any]:
    """Compose the quarterly investor update payload (KPIs + cap table)."""
    kpis = collect_kpis(session, as_of)
    quarter = (as_of.month - 1) // 3 + 1
    return compose_investor_update(f"{as_of.year}-Q{quarter}", kpis, cap_table(session))
