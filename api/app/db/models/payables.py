"""Payables domain tables (PRD §3.4). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    pan: Mapped[str | None] = mapped_column(String)
    gstin: Mapped[str | None] = mapped_column(String)
    msme_status: Mapped[int] = mapped_column(Integer, default=0)  # 1 = registered MSME
    msme_type: Mapped[str | None] = mapped_column(String)  # micro/small/medium
    bank_account: Mapped[str | None] = mapped_column(String)
    ifsc: Mapped[str | None] = mapped_column(String)
    payment_terms: Mapped[int] = mapped_column(Integer, default=30)  # days
    tds_section: Mapped[str | None] = mapped_column(String)  # 194C/194J/194H/194I
    payee_type: Mapped[str] = mapped_column(String, default="company")  # individual/huf/company
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    po_date: Mapped[str] = mapped_column(String, nullable=False)
    delivery_date: Mapped[str | None] = mapped_column(String)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    received_amount: Mapped[int] = mapped_column(Integer, default=0)  # GRN value, paise
    status: Mapped[str] = mapped_column(String, default="open")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bill_number: Mapped[str] = mapped_column(String, nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    po_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    bill_date: Mapped[str] = mapped_column(String, nullable=False)
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)  # paise (taxable)
    gst_amount: Mapped[int] = mapped_column(Integer, default=0)
    igst_amount: Mapped[int] = mapped_column(Integer, default=0)
    cgst_amount: Mapped[int] = mapped_column(Integer, default=0)
    sgst_amount: Mapped[int] = mapped_column(Integer, default=0)
    tds_amount: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    itc_eligible: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="open")
    paid_date: Mapped[str | None] = mapped_column(String)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)
