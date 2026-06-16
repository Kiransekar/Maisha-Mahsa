"""GST domain tables (PRD §3.6). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GstReturn(Base):
    __tablename__ = "gst_returns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    return_type: Mapped[str] = mapped_column(String, nullable=False)  # GSTR-1 / GSTR-3B / ...
    filing_period: Mapped[str] = mapped_column(String, nullable=False)  # "YYYY-MM"
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    filed_date: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    json_file_path: Mapped[str | None] = mapped_column(String)
    acknowledgement: Mapped[str | None] = mapped_column(String)
    tax_payable: Mapped[int] = mapped_column(Integer, default=0)  # paise (cash)
    tax_paid: Mapped[int] = mapped_column(Integer, default=0)
    late_fee: Mapped[int] = mapped_column(Integer, default=0)
    interest: Mapped[int] = mapped_column(Integer, default=0)


class ItcRegister(Base):
    __tablename__ = "itc_register"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer)
    bill_id: Mapped[int | None] = mapped_column(Integer)
    gstin_supplier: Mapped[str] = mapped_column(String, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String, nullable=False)
    invoice_date: Mapped[str] = mapped_column(String, nullable=False)
    taxable_value: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    igst: Mapped[int] = mapped_column(Integer, default=0)
    cgst: Mapped[int] = mapped_column(Integer, default=0)
    sgst: Mapped[int] = mapped_column(Integer, default=0)
    total_tax: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_itc: Mapped[int] = mapped_column(Integer, default=1)  # 1 = eligible
    in_2b: Mapped[int] = mapped_column(Integer, default=0)  # 1 = appears in GSTR-2B
    claimed_in_return: Mapped[str | None] = mapped_column(String)
