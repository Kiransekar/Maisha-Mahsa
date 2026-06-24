"""Payroll eval cases. Ground truth mirrors the validated net-pay computation in
``tests/unit/payroll/test_payroll_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.db.models.payroll import Employee
from app.domains.payroll.service import PayrollService
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_one_employee(session: Session) -> None:
    emp = Employee(employee_code="E1", name="Asha", date_of_joining="2021-04-01", state="MH")
    session.add(emp)
    session.flush()
    PayrollService().set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="payroll-net-pay",
        domain="payroll",
        query="What is the minimum monthly net pay across active staff?",
        seed=_seed_one_employee,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"min_net_pay_paise": "9800000"},  # ₹98,000 after PF/PT/TDS
        ),
        stub_claim=ActionClaim(
            domain="payroll",
            narrative="Lowest monthly net pay is ₹98,000 after PF, PT and TDS.",
            claims={"min_net_pay_paise": "9800000"},
        ),
    ),
]
