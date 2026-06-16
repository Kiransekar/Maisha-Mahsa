"""Pydantic request/response models for the expense API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel


class NewClaim(BaseModel):
    employee_id: int | None = None
    claim_date: str
    expense_date: str
    category: str
    amount: int  # paise
    gst_amount: int = 0
    vendor_name: str | None = None
    description: str | None = None


class ClaimResult(BaseModel):
    claim_id: int
    amount: int
    over_policy: bool
    policy_limit: int | None
    excess: int
    petty_cash_eligible: bool


class ReceiptText(BaseModel):
    ocr_text: str
