"""Pydantic request/response models for the forecast API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CashProjectionInput(BaseModel):
    opening_cash: int  # paise
    monthly_net_change: list[int] = Field(default_factory=list)  # signed paise per month


class ScenarioInput(BaseModel):
    opening_cash: int
    base_revenue: int  # monthly paise
    base_cost: int  # monthly paise
    horizon_months: int = 12
    revenue_mult: float = 1.0
    extra_cost: int = 0  # e.g. extra hires per month


class UnitEconomicsInput(BaseModel):
    sales_marketing_spend: int  # paise
    new_customers: int
    arpu: int  # monthly paise per account
    gross_margin: float  # fraction
    lifetime_months: int


class RecordForecast(BaseModel):
    forecast_date: str
    scenario: str = "base"
    horizon_months: int = 12
    opening_cash: int
    monthly_net_change: list[int] = Field(default_factory=list)
