"""Forecast service: budget variance, rolling cash projection, scenarios, unit economics,
and the forecast health snapshot for Mahsa. Deterministic; money in paise.

Forecast has no Mahsa sub-vector (not one of the 8 health domains); Mahsa enforces
FORECAST-001 (projected cash must not go negative) on the snapshot's ``forecast_min_cash``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.forecast import Forecast
from app.domains.forecast import forecast_calc
from app.domains.forecast.manifest import MANIFEST


class ForecastService(BaseDomainService):
    domain = "forecast"
    keywords = (
        "budget",
        "forecast",
        "scenario",
        "runway forecast",
        "burn multiple",
        "unit economics",
        "cac",
        "ltv",
        "headcount",
    )
    manifest = MANIFEST

    # ---- projections ----------------------------------------------------------------

    def project_cash(self, opening_cash: int, monthly_net_change: list[int]) -> dict[str, Any]:
        return forecast_calc.project_cash(opening_cash, monthly_net_change)

    def scenario(
        self,
        *,
        opening_cash: int,
        base_revenue: int,
        base_cost: int,
        horizon_months: int = 12,
        revenue_mult: float = 1.0,
        extra_cost: int = 0,
    ) -> dict[str, Any]:
        net = forecast_calc.scenario_net_change(
            base_revenue, base_cost, revenue_mult=revenue_mult, extra_cost=extra_cost
        )
        projection = forecast_calc.project_cash(opening_cash, [net] * horizon_months)
        return {"monthly_net_change": net, **projection}

    def unit_economics(self, **kwargs: Any) -> dict[str, Any]:
        return forecast_calc.unit_economics(**kwargs)

    # ---- persistence ----------------------------------------------------------------

    def record_forecast(
        self,
        session: Session,
        *,
        forecast_date: str,
        opening_cash: int,
        monthly_net_change: list[int],
        scenario: str = "base",
        horizon_months: int = 12,
    ) -> dict[str, Any]:
        projection = forecast_calc.project_cash(opening_cash, monthly_net_change)
        row = Forecast(
            forecast_date=forecast_date,
            horizon_months=horizon_months,
            scenario=scenario,
            cash_forecast=projection["min_cash"],
            runway_forecast=projection["months_to_zero"],
        )
        session.add(row)
        session.flush()
        return {"forecast_id": row.id, **projection}

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        latest = session.scalars(select(Forecast).order_by(Forecast.id.desc()).limit(1)).first()
        min_cash = int(latest.cash_forecast) if latest and latest.cash_forecast is not None else 0
        runway = latest.runway_forecast if latest else None
        return {
            "as_of": anchor.isoformat(),
            "metrics": {
                # consumed by FORECAST-001 (must be >= 0)
                "forecast_min_cash_paise": min_cash,
                "forecast_runway_months": runway if runway is not None else 999,
            },
        }
