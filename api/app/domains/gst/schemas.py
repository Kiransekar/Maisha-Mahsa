"""Pydantic request/response models for the GST API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaxHeads(BaseModel):
    igst: int = 0
    cgst: int = 0
    sgst: int = 0


class Gstr3bInput(BaseModel):
    filing_period: str  # "YYYY-MM"
    due_date: str  # ISO
    filed_date: str | None = None
    is_nil: bool = False
    output: TaxHeads
    itc_available: TaxHeads


class Gstr3bResult(BaseModel):
    gst_return_id: int
    filing_period: str
    cash: dict[str, int]
    cash_total: int
    late_fee: int
    interest: int
    total_payable: int


class SupplyLine(BaseModel):
    invoice_no: str
    taxable: int
    igst: int = 0
    cgst: int = 0
    sgst: int = 0
    hsn: str | None = None
    gstin: str | None = None
    qty: int = 0


class Gstr1Input(BaseModel):
    filing_period: str
    lines: list[SupplyLine] = Field(default_factory=list)
