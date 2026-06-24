"""EPFO ECR text-file generation — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.db.models.payroll import Employee
from app.domains.payroll import statutory
from app.domains.payroll.ecr import ECR_DELIMITER, EcrMember, build_ecr
from app.domains.payroll.service import PayrollService


def test_eps_and_diff_split_at_ceiling() -> None:
    basic = Paise.from_rupees(50000)  # above the ₹15,000 PF ceiling
    # EPS = 8.33% of 15,000 = ₹1,250; employer total 12% of 15,000 = ₹1,800; diff = ₹550
    assert statutory.eps_employer(basic) == Paise.from_rupees(1250)
    assert statutory.epf_employer_diff(basic) == Paise.from_rupees(550)
    assert statutory.pf_employee(basic) == Paise.from_rupees(1800)


def test_member_line_has_11_delimited_fields() -> None:
    m = EcrMember(
        uan="100100100100", member_name="Asha", gross_wages=100000, epf_wages=15000,
        eps_wages=15000, edli_wages=15000, epf_contri_remitted=1800, eps_contri_remitted=1250,
        epf_eps_diff_remitted=550,
    )
    line = m.to_line()
    parts = line.split(ECR_DELIMITER)
    assert len(parts) == 11
    assert parts[0] == "100100100100" and parts[1] == "Asha"
    assert parts[7] == "1250" and parts[8] == "550"  # EPS, EPF-EPS diff
    assert parts[9] == "0" and parts[10] == "0"  # NCP days, refund


def test_build_ecr_one_line_per_member() -> None:
    rows = [
        EcrMember("1", "A", 100000, 15000, 15000, 15000, 1800, 1250, 550),
        EcrMember("2", "B", 80000, 15000, 15000, 15000, 1800, 1250, 550),
    ]
    out = build_ecr(rows)
    assert out.count("\n") == 1 and len(out.splitlines()) == 2


def test_service_ecr_text(session) -> None:  # type: ignore[no-untyped-def]
    svc = PayrollService()
    emp = Employee(employee_code="E1", name="Asha", date_of_joining="2021-04-01",
                   state="MH", uan="100100100100")
    session.add(emp)
    session.flush()
    svc.set_salary_structure(
        session, emp.id, effective_from="2026-04-01",
        basic=Paise.from_rupees(50000), hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    text = svc.ecr_text(session, period="2026-06")
    line = text.splitlines()[0].split(ECR_DELIMITER)
    assert line[0] == "100100100100"  # UAN
    assert line[3] == "15000"  # EPF wages capped at ceiling
    assert line[6] == "1800" and line[7] == "1250" and line[8] == "550"
