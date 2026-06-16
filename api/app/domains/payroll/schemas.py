"""Pydantic request/response models for the payroll API."""

from __future__ import annotations

from pydantic import BaseModel


class NewEmployee(BaseModel):
    employee_code: str
    name: str
    date_of_joining: str  # ISO date
    state: str | None = None  # for PT
    pan: str | None = None
    uan: str | None = None


class SalaryInput(BaseModel):
    """Monthly component inputs in **paise**. Statutory deductions are derived, not supplied."""

    effective_from: str
    basic: int
    hra: int
    lta: int = 0
    special_allowance: int = 0


class ComputedSalary(BaseModel):
    gross_salary: int
    employee_pf: int
    employer_pf: int
    employee_esi: int
    employer_esi: int
    professional_tax: int
    tds_monthly: int
    net_salary: int
    ctc: int


class PayrollRunResult(BaseModel):
    payroll_run_id: int
    month_year: str
    employee_count: int
    total_gross: int
    total_deductions: int
    total_net: int
    total_pf_employer: int
    total_esi_employer: int
    min_net_pay: int
