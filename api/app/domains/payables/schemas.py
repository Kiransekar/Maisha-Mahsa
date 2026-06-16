"""Pydantic request/response models for the payables API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel


class NewVendor(BaseModel):
    name: str
    gstin: str | None = None
    pan: str | None = None
    msme_status: bool = False
    payment_terms: int = 30
    tds_section: str | None = None
    payee_type: str = "company"


class NewBill(BaseModel):
    bill_number: str
    vendor_id: int
    bill_date: str  # ISO
    subtotal: int  # paise (taxable)
    gst_amount: int = 0
    igst_amount: int = 0
    cgst_amount: int = 0
    sgst_amount: int = 0
    po_id: int | None = None
    itc_eligible: bool = True
    tds_category: str | None = None  # e.g. "technical", "plant"


class BillResult(BaseModel):
    bill_id: int
    bill_number: str
    subtotal: int
    tds_amount: int
    tds_section: str | None
    total_amount: int
    due_date: str
    three_way_match: dict | None = None
