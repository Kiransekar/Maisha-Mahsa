from datetime import date

from sqlalchemy import select

from app.core.money import Paise
from app.db.models.payroll import Employee, PayrollEntry
from app.domains.payroll.service import PayrollService, compute_components


def test_compute_components_high_earner_no_esi():
    # basic 50k, hra 20k, special 30k -> gross ₹1,00,000; ESI nil (> ceiling);
    # PF ₹1,800; PT(MH) ₹200; annual ₹12L -> taxable ₹11.25L -> TDS nil
    comp = compute_components(
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        lta=0,
        special_allowance=Paise.from_rupees(30000),
        state="MH",
        month=6,
    )
    assert comp["gross_salary"] == Paise.from_rupees(100000)
    assert comp["employee_pf"] == Paise.from_rupees(1800)
    assert comp["employee_esi"] == 0
    assert comp["professional_tax"] == Paise.from_rupees(200)
    assert comp["tds_monthly"] == 0
    assert comp["net_salary"] == Paise.from_rupees(98000)  # 100000 - 1800 - 200
    assert comp["ctc"] == Paise.from_rupees(101800)  # gross + employer PF


def test_compute_components_with_tds():
    # gross ₹1,50,000 -> annual ₹18L -> monthly TDS ₹12,567
    comp = compute_components(
        basic=Paise.from_rupees(80000),
        hra=Paise.from_rupees(40000),
        lta=0,
        special_allowance=Paise.from_rupees(30000),
        state="MH",
        month=6,
    )
    assert comp["tds_monthly"] == Paise.from_rupees(12567)
    # net = 150000 - 1800(pf) - 200(pt) - 12567(tds) = 135433
    assert comp["net_salary"] == Paise.from_rupees(135433)


def _employee(session, code="E1", state="MH"):
    emp = Employee(employee_code=code, name="Asha", date_of_joining="2021-04-01", state=state)
    session.add(emp)
    session.flush()
    return emp


def test_run_payroll_totals(session):
    svc = PayrollService()
    emp = _employee(session)
    svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    result = svc.run_payroll(session, "2026-06", run_date="2026-06-30")
    assert result["employee_count"] == 1
    assert result["total_gross"] == Paise.from_rupees(100000)
    assert result["total_net"] == Paise.from_rupees(98000)
    assert result["total_pf_employer"] == Paise.from_rupees(1800)
    assert result["min_net_pay"] == Paise.from_rupees(98000)

    entries = session.scalars(select(PayrollEntry)).all()
    assert len(entries) == 1
    assert entries[0].net_pay == Paise.from_rupees(98000)


def test_february_pt_special_applies_in_run(session):
    svc = PayrollService()
    emp = _employee(session)
    svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-01-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    feb = svc.run_payroll(session, "2026-02", run_date="2026-02-28")
    # PT ₹300 in Feb -> net = 100000 - 1800 - 300 = 97900
    assert feb["total_net"] == Paise.from_rupees(97900)


def test_build_snapshot_metrics(session):
    svc = PayrollService()
    emp = _employee(session)
    svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    m = snap["metrics"]
    assert m["min_net_pay_paise"] == Paise.from_rupees(98000)
    assert m["pf_compliance"] == 1.0
    assert m["bonus_reserve"] == 1.0
