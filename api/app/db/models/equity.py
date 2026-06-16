"""Equity domain tables (PRD §3.9). Money columns are INTEGER **paise**; share counts are
plain integers."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Shareholder(Base):
    __tablename__ = "shareholders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # founder/investor/esop/advisor
    pan: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    investment_date: Mapped[str | None] = mapped_column(String)
    investment_amount: Mapped[int] = mapped_column(Integer, default=0)  # paise
    share_class: Mapped[str | None] = mapped_column(String)
    shares_held: Mapped[int] = mapped_column(Integer, default=0)
    share_premium: Mapped[int] = mapped_column(Integer, default=0)  # paise
    pre_money_valuation: Mapped[int | None] = mapped_column(Integer)
    post_money_valuation: Mapped[int | None] = mapped_column(Integer)
    anti_dilution: Mapped[str | None] = mapped_column(String)
    liquidation_preference: Mapped[float | None] = mapped_column()
    board_seat: Mapped[int] = mapped_column(Integer, default=0)


class SafeNote(Base):
    __tablename__ = "safe_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    investor_id: Mapped[int] = mapped_column(ForeignKey("shareholders.id"), nullable=False)
    issue_date: Mapped[str] = mapped_column(String, nullable=False)
    investment_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    valuation_cap: Mapped[int | None] = mapped_column(Integer)  # paise
    discount_rate: Mapped[float] = mapped_column(default=0.0)  # e.g. 0.20
    pro_rata_rights: Mapped[int] = mapped_column(Integer, default=1)
    conversion_trigger: Mapped[str | None] = mapped_column(String)
    converted: Mapped[int] = mapped_column(Integer, default=0)
    conversion_date: Mapped[str | None] = mapped_column(String)
    shares_issued: Mapped[int | None] = mapped_column(Integer)


class CapTableSnapshot(Base):
    __tablename__ = "cap_table_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[str] = mapped_column(String, nullable=False)
    total_shares: Mapped[int] = mapped_column(Integer, nullable=False)
    total_diluted_shares: Mapped[int] = mapped_column(Integer, nullable=False)
    esop_pool_shares: Mapped[int] = mapped_column(Integer, default=0)
    esop_pool_pct: Mapped[float] = mapped_column(default=0.0)
    esop_board_approved: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_json: Mapped[str] = mapped_column(String, nullable=False)
