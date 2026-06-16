"""Pydantic request/response models for the revenue API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NewCustomer(BaseModel):
    name: str
    gstin: str | None = None
    pan: str | None = None
    state: str | None = None
    payment_terms: int = 30
    tds_applicable: bool = False
    tds_rate: float = 0.0


class InvoiceLine(BaseModel):
    description: str
    quantity: int = 1
    rate: int  # paise per unit
    hsn_code: str | None = None


class NewInvoice(BaseModel):
    invoice_number: str
    customer_id: int
    invoice_date: str  # ISO
    gst_rate: float = 18.0
    lines: list[InvoiceLine] = Field(default_factory=list)
    irn: str | None = None


class InvoiceResult(BaseModel):
    invoice_id: int
    invoice_number: str
    subtotal: int
    igst_amount: int
    cgst_amount: int
    sgst_amount: int
    total_amount: int
    tds_amount: int
    net_receivable: int
    due_date: str
