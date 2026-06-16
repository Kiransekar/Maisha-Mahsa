"""Tax domain tables (PRD §3.7). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TdsReturn(Base):
    __tablename__ = "tds_returns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    return_type: Mapped[str] = mapped_column(String, nullable=False)  # 24Q / 26Q / 27Q
    quarter: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "2026-Q1"
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    filed_date: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    total_deducted: Mapped[int] = mapped_column(Integer, default=0)  # paise
    total_deposited: Mapped[int] = mapped_column(Integer, default=0)
    late_filing_fee: Mapped[int] = mapped_column(Integer, default=0)
    json_file_path: Mapped[str | None] = mapped_column(String)


class TdsEntry(Base):
    __tablename__ = "tds_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tds_return_id: Mapped[int | None] = mapped_column(ForeignKey("tds_returns.id"))
    deductee_name: Mapped[str] = mapped_column(String, nullable=False)
    deductee_pan: Mapped[str | None] = mapped_column(String)
    section: Mapped[str] = mapped_column(String, nullable=False)
    payment_date: Mapped[str] = mapped_column(String, nullable=False)
    payment_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    tds_rate: Mapped[float] = mapped_column(default=0.0)
    tds_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    surcharge: Mapped[int] = mapped_column(Integer, default=0)
    cess: Mapped[int] = mapped_column(Integer, default=0)
    total_tds: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_date: Mapped[str | None] = mapped_column(String)
    challan_number: Mapped[str | None] = mapped_column(String)
    bsr_code: Mapped[str | None] = mapped_column(String)


class AdvanceTax(Base):
    __tablename__ = "advance_tax"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fy: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "2026-27"
    installment: Mapped[str] = mapped_column(String, nullable=False)  # Q1/Q2/Q3/Q4
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    paid_date: Mapped[str | None] = mapped_column(String)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    challan_number: Mapped[str | None] = mapped_column(String)
    bsr_code: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
