"""Payslip + Form-16 PDF generation — deferred features (ReportLab)."""

from __future__ import annotations

from app.core import pdf
from app.core.money import Paise
from app.db.models.payroll import Employee
from app.domains.payroll.service import PayrollService


def test_payslip_pdf_builder_returns_pdf_bytes() -> None:
    out = pdf.payslip_pdf(
        {
            "company": "Acme",
            "employee_name": "Asha",
            "employee_code": "E1",
            "period": "2026-06",
            "earnings": [("Basic", Paise.from_rupees(50000)), ("HRA", Paise.from_rupees(20000))],
            "deductions": [
                ("PF (employee)", Paise.from_rupees(1800)),
                ("TDS", Paise.from_rupees(12000)),
            ],
            "gross": Paise.from_rupees(70000),
            "total_deductions": Paise.from_rupees(13800),
            "net": Paise.from_rupees(56200),
        }
    )
    assert out[:5] == b"%PDF-" and len(out) > 800


def test_form16_pdf_builder_returns_pdf_bytes() -> None:
    out = pdf.form16_pdf(
        {
            "company": "Acme",
            "tan": "DELA12345B",
            "employee_name": "Asha",
            "pan": "ABCDE1234F",
            "financial_year": "2025-26",
            "assessment_year": "2026-27",
            "rows": [("Gross salary (annual)", Paise.from_rupees(1200000))],
            "total_tax_deducted": Paise.from_rupees(150000),
        }
    )
    assert out[:5] == b"%PDF-"


def _employee_with_salary(session) -> int:  # type: ignore[no-untyped-def]
    emp = Employee(
        employee_code="E1", name="Asha", date_of_joining="2021-04-01", state="MH", pan="ABCDE1234F"
    )
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
    return emp.id


def test_service_payslip(session) -> None:  # type: ignore[no-untyped-def]
    eid = _employee_with_salary(session)
    out = PayrollService().payslip(session, eid, period="2026-06", company="Maisha-Mahsa")
    assert out[:5] == b"%PDF-"


def test_service_form16(session) -> None:  # type: ignore[no-untyped-def]
    eid = _employee_with_salary(session)  # salary effective 2026-04-01 -> FY 2026-27
    out = PayrollService().form16(session, eid, financial_year="2026-27")
    assert out[:5] == b"%PDF-"


def test_payslip_unknown_employee_raises(session) -> None:  # type: ignore[no-untyped-def]
    try:
        PayrollService().payslip(session, 9999, period="2026-06")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
