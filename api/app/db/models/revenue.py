"""Revenue domain tables (PRD §3.3). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    pan: Mapped[str | None] = mapped_column(String)
    gstin: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)  # place of supply (intra/inter-state)
    payment_terms: Mapped[int] = mapped_column(Integer, default=30)  # days
    tds_applicable: Mapped[int] = mapped_column(Integer, default=0)
    tds_section: Mapped[str | None] = mapped_column(String)
    tds_rate: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    invoice_date: Mapped[str] = mapped_column(String, nullable=False)
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)  # paise (taxable)
    gst_rate: Mapped[float] = mapped_column(default=0.0)
    igst_amount: Mapped[int] = mapped_column(Integer, default=0)
    cgst_amount: Mapped[int] = mapped_column(Integer, default=0)
    sgst_amount: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    tds_amount: Mapped[int] = mapped_column(Integer, default=0)
    net_receivable: Mapped[int] = mapped_column(Integer, nullable=False)
    irn: Mapped[str | None] = mapped_column(String)
    qr_code_path: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft")
    paid_date: Mapped[str | None] = mapped_column(String)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    hsn_code: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    rate: Mapped[int] = mapped_column(Integer, nullable=False)  # paise per unit
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise


class CreditNote(Base):
    __tablename__ = "credit_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    credit_note_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    issue_date: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    gst_adjustment: Mapped[int] = mapped_column(Integer, default=0)
