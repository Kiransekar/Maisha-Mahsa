"""Forecast FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.landing import mask_field
from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.forecast.schemas import (
    CashProjectionInput,
    RecordForecast,
    ScenarioInput,
    UnitEconomicsInput,
)
from app.domains.forecast.service import ForecastService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/forecast",
    tags=["forecast"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = ForecastService()


@router.post("/project")
def project(body: CashProjectionInput) -> dict:
    return _service.project_cash(body.opening_cash, body.monthly_net_change)


@router.post("/scenario")
def scenario(body: ScenarioInput) -> dict:
    return _service.scenario(
        opening_cash=body.opening_cash,
        base_revenue=body.base_revenue,
        base_cost=body.base_cost,
        horizon_months=body.horizon_months,
        revenue_mult=body.revenue_mult,
        extra_cost=body.extra_cost,
    )


@router.post("/unit-economics")
def unit_economics(
    body: UnitEconomicsInput, principal: Principal = Depends(resolve_principal)
) -> dict:
    # T11: margin/unit-economics fields (cac/ltv/payback/ratio) are confidential — masked at
    # the serialization boundary for any role below that clearance (today: Investor, whose
    # report links must never carry unit economics; the read gate already 403s them wholesale,
    # so this is the field-level backstop the WS7 contract's T11 row requires).
    result = _service.unit_economics(**body.model_dump())
    return {k: mask_field(principal.role, k, v) for k, v in result.items()}


@router.post("/forecasts", dependencies=[Depends(require(Capability.WRITE))])
def record_forecast(body: RecordForecast, db: Session = Depends(get_session)) -> dict:
    result = _service.record_forecast(
        db,
        forecast_date=body.forecast_date,
        opening_cash=body.opening_cash,
        monthly_net_change=body.monthly_net_change,
        scenario=body.scenario,
        horizon_months=body.horizon_months,
    )
    db.commit()
    return result


@router.post("/fold")
async def fold(
    as_of: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    outcome = await run_loop(
        session=db,
        mahsa=mahsa,
        service=_service,
        timestamp=datetime.now(UTC).isoformat(),
        as_of=anchor,
        action="forecast.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "audit_hash": outcome.audit_hash,
    }
