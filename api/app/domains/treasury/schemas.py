"""Pydantic request/response models for the treasury API."""

from __future__ import annotations

from pydantic import BaseModel


class ImportResult(BaseModel):
    account_id: int
    rows_imported: int
    rows_skipped: int
    closing_balance_paise: int


class CashPosition(BaseModel):
    total_cash_paise: int
    account_count: int
    largest_account_share: float
    by_account: dict[str, int]  # bank_name -> balance paise


class TreasuryMetrics(BaseModel):
    as_of: str
    window_months: int
    cash_paise: int
    monthly_burn_paise: int
    monthly_revenue_paise: int
    net_burn_paise: int
    runway_months: float | None  # None == infinite (not burning)
