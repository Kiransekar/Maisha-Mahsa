"""Pydantic request/response models for the equity API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel


class NewShareholder(BaseModel):
    name: str
    category: str  # founder/investor/esop/advisor
    shares_held: int = 0
    investment_amount: int = 0
    board_seat: bool = False


class SafeConversionInput(BaseModel):
    investment: int  # paise
    valuation_cap: int | None = None  # paise
    discount_rate: float = 0.0
    round_price_per_share: int  # paise
    pre_round_shares: int


class SafeConversionResult(BaseModel):
    conversion_price_paise: int
    shares_issued: int
