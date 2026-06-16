"""Pydantic request/response models for the tax API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel


class TdsReturnInput(BaseModel):
    return_type: str  # 24Q / 26Q / 27Q
    quarter: str  # "2026-Q1"
    due_date: str
    total_deducted: int  # paise
    filed_date: str | None = None


class TdsReturnResult(BaseModel):
    tds_return_id: int
    return_type: str
    quarter: str
    total_deducted: int
    late_filing_fee: int
    status: str


class AdvanceTaxInput(BaseModel):
    fy: str  # "2026-27"
    installment: str  # Q1/Q2/Q3/Q4
    due_date: str
    amount: int  # paise
    paid_date: str | None = None


class Interest234cInput(BaseModel):
    total_liability: int  # paise
    cumulative_paid: list[int]  # 4 cumulative amounts, paise
