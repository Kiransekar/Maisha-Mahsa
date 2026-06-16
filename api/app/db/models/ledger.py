"""Ledger / accounting tables (PRD §3.8). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChartOfAccounts(Base):
    __tablename__ = "chart_of_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # asset / liability / equity / income / expense
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    sub_type: Mapped[str | None] = mapped_column(String)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chart_of_accounts.id"))
    is_bank_account: Mapped[int] = mapped_column(Integer, default=0)
    is_cash_account: Mapped[int] = mapped_column(Integer, default=0)
    opening_balance: Mapped[int] = mapped_column(Integer, default=0)  # paise


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_date: Mapped[str] = mapped_column(String, nullable=False)
    reference: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String)  # manual / payroll / gst / depreciation
    total_debit: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    total_credit: Mapped[int] = mapped_column(Integer, nullable=False)
    is_auto_generated: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("chart_of_accounts.id"), nullable=False)
    debit: Mapped[int] = mapped_column(Integer, default=0)  # paise
    credit: Mapped[int] = mapped_column(Integer, default=0)  # paise
    description: Mapped[str | None] = mapped_column(String)


class FixedAsset(Base):
    __tablename__ = "fixed_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_name: Mapped[str] = mapped_column(String, nullable=False)
    asset_code: Mapped[str | None] = mapped_column(String, unique=True)
    purchase_date: Mapped[str] = mapped_column(String, nullable=False)
    purchase_cost: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    salvage_value: Mapped[int] = mapped_column(Integer, default=0)
    useful_life_years: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method: Mapped[str] = mapped_column(String, default="wdv")  # slm/wdv
    depreciation_rate: Mapped[float] = mapped_column(default=0.0)  # for WDV
    accumulated_depreciation: Mapped[int] = mapped_column(Integer, default=0)  # paise
    wdv: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    disposal_date: Mapped[str | None] = mapped_column(String)
    disposal_amount: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="active")
