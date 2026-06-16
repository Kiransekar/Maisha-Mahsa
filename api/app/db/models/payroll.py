"""Payroll domain tables (PRD §3.5). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    pan: Mapped[str | None] = mapped_column(String)
    uan: Mapped[str | None] = mapped_column(String)
    esi_ip_number: Mapped[str | None] = mapped_column(String)
    date_of_joining: Mapped[str] = mapped_column(String, nullable=False)
    date_of_exit: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    state: Mapped[str | None] = mapped_column(String)  # for PT/LWF state rules
    bank_account: Mapped[str | None] = mapped_column(String)
    ifsc: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())


class SalaryStructure(Base):
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    effective_from: Mapped[str] = mapped_column(String, nullable=False)
    basic: Mapped[int] = mapped_column(Integer, nullable=False)  # paise (monthly)
    hra: Mapped[int] = mapped_column(Integer, nullable=False)
    lta: Mapped[int] = mapped_column(Integer, default=0)
    special_allowance: Mapped[int] = mapped_column(Integer, default=0)
    employer_pf: Mapped[int] = mapped_column(Integer, nullable=False)
    employer_esi: Mapped[int] = mapped_column(Integer, default=0)
    employee_pf: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_esi: Mapped[int] = mapped_column(Integer, default=0)
    professional_tax: Mapped[int] = mapped_column(Integer, default=0)
    tds_monthly: Mapped[int] = mapped_column(Integer, default=0)
    gross_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    net_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    ctc: Mapped[int] = mapped_column(Integer, nullable=False)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month_year: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "2026-06"
    run_date: Mapped[str] = mapped_column(String, nullable=False)
    total_gross: Mapped[int] = mapped_column(Integer, default=0)
    total_deductions: Mapped[int] = mapped_column(Integer, default=0)
    total_net: Mapped[int] = mapped_column(Integer, default=0)
    total_pf_employer: Mapped[int] = mapped_column(Integer, default=0)
    total_esi_employer: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="draft")
    ecr_generated: Mapped[int] = mapped_column(Integer, default=0)
    ecr_file_path: Mapped[str | None] = mapped_column(String)


class PayrollEntry(Base):
    __tablename__ = "payroll_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    gross: Mapped[int] = mapped_column(Integer, nullable=False)
    basic: Mapped[int] = mapped_column(Integer, nullable=False)
    hra: Mapped[int] = mapped_column(Integer, nullable=False)
    lta: Mapped[int] = mapped_column(Integer, default=0)
    special_allowance: Mapped[int] = mapped_column(Integer, default=0)
    employee_pf: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_esi: Mapped[int] = mapped_column(Integer, default=0)
    professional_tax: Mapped[int] = mapped_column(Integer, default=0)
    tds: Mapped[int] = mapped_column(Integer, default=0)
    other_deductions: Mapped[int] = mapped_column(Integer, default=0)
    employer_pf: Mapped[int] = mapped_column(Integer, default=0)
    employer_esi: Mapped[int] = mapped_column(Integer, default=0)
    net_pay: Mapped[int] = mapped_column(Integer, nullable=False)


class EsopGrant(Base):
    __tablename__ = "esop_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    grant_date: Mapped[str] = mapped_column(String, nullable=False)
    vesting_start_date: Mapped[str] = mapped_column(String, nullable=False)
    cliff_months: Mapped[int] = mapped_column(Integer, default=12)
    vesting_period_months: Mapped[int] = mapped_column(Integer, default=48)
    total_options: Mapped[int] = mapped_column(Integer, nullable=False)
    exercise_price: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    vested_options: Mapped[int] = mapped_column(Integer, default=0)
    exercised_options: Mapped[int] = mapped_column(Integer, default=0)
    forfeited_options: Mapped[int] = mapped_column(Integer, default=0)
