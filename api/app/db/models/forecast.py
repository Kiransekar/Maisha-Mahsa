"""Forecast / budgeting tables (PRD §3.10). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fy: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String)
    jan: Mapped[int] = mapped_column(Integer, default=0)
    feb: Mapped[int] = mapped_column(Integer, default=0)
    mar: Mapped[int] = mapped_column(Integer, default=0)
    apr: Mapped[int] = mapped_column(Integer, default=0)
    may: Mapped[int] = mapped_column(Integer, default=0)
    jun: Mapped[int] = mapped_column(Integer, default=0)
    jul: Mapped[int] = mapped_column(Integer, default=0)
    aug: Mapped[int] = mapped_column(Integer, default=0)
    sep: Mapped[int] = mapped_column(Integer, default=0)
    oct: Mapped[int] = mapped_column(Integer, default=0)
    nov: Mapped[int] = mapped_column(Integer, default=0)
    dec: Mapped[int] = mapped_column(Integer, default=0)
    annual_total: Mapped[int] = mapped_column(Integer, nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_date: Mapped[str] = mapped_column(String, nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, default=12)
    scenario: Mapped[str] = mapped_column(String, default="base")
    revenue_forecast: Mapped[int | None] = mapped_column(Integer)  # paise
    burn_forecast: Mapped[int | None] = mapped_column(Integer)  # paise/month
    headcount_forecast: Mapped[int | None] = mapped_column(Integer)
    cash_forecast: Mapped[int | None] = mapped_column(Integer)  # projected min cash, paise
    runway_forecast: Mapped[float | None] = mapped_column()  # months
    assumptions: Mapped[str | None] = mapped_column(String)
