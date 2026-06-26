"""Payroll: expanded Professional Tax states, Labour Welfare Fund calendars, and
leave/loss-of-pay (features pt / lwf / leave)."""

from app.core.money import Paise
from app.db.models.payroll import Employee
from app.domains.payroll import statutory as s
from app.domains.payroll.service import PayrollService, compute_components


def test_pt_additional_states():
    # West Bengal graded slabs
    assert s.professional_tax("WB", Paise.from_rupees(9000), 6) == 0
    assert s.professional_tax("WB", Paise.from_rupees(12000), 6) == Paise.from_rupees(110)
    assert s.professional_tax("WB", Paise.from_rupees(30000), 6) == Paise.from_rupees(150)
    assert s.professional_tax("WB", Paise.from_rupees(50000), 6) == Paise.from_rupees(200)
    # Gujarat
    assert s.professional_tax("GJ", Paise.from_rupees(10000), 6) == 0
    assert s.professional_tax("GJ", Paise.from_rupees(20000), 6) == Paise.from_rupees(200)
    # Andhra / Telangana
    assert s.professional_tax("AP", Paise.from_rupees(18000), 6) == Paise.from_rupees(150)
    assert s.professional_tax("TS", Paise.from_rupees(25000), 6) == Paise.from_rupees(200)
    # still unmodelled -> 0
    assert s.professional_tax("TN", Paise.from_rupees(50000), 6) == 0


def test_lwf_due_only_in_due_months():
    # Maharashtra: half-yearly (Jun, Dec), ₹25 employee + ₹75 employer
    assert s.labour_welfare_fund("MH", 6) == (Paise.from_rupees(25), Paise.from_rupees(75))
    assert s.labour_welfare_fund("MH", 12) == (Paise.from_rupees(25), Paise.from_rupees(75))
    assert s.labour_welfare_fund("MH", 7) == (Paise(0), Paise(0))  # not a due month
    # Karnataka: annual (Dec only)
    assert s.labour_welfare_fund("KA", 12) == (Paise.from_rupees(20), Paise.from_rupees(40))
    assert s.labour_welfare_fund("KA", 6) == (Paise(0), Paise(0))
    # unmodelled state
    assert s.labour_welfare_fund("DL", 6) == (Paise(0), Paise(0))
    assert s.lwf_is_modelled("MH") and not s.lwf_is_modelled("DL")


def test_loss_of_pay_prorates_gross():
    gross = Paise.from_rupees(30000)
    assert s.loss_of_pay(gross, 0, 30) == 0  # no LOP
    assert s.loss_of_pay(gross, 3, 30) == Paise.from_rupees(3000)  # 3/30 of 30000
    # capped at the month
    assert s.loss_of_pay(gross, 40, 30) == gross


def test_leave_balance():
    assert s.leave_balance(12, 1.5, 4) == 9.5
    assert s.leave_balance(2, 0, 5) == 0.0  # floored at zero


def test_compute_components_lop_reduces_net():
    full = compute_components(
        basic=Paise.from_rupees(20000), hra=0, lta=0, special_allowance=0,
        state="MH", month=7,
    )
    lop = compute_components(
        basic=Paise.from_rupees(20000), hra=0, lta=0, special_allowance=0,
        state="MH", month=7, lop_days=3, days_in_month=30,
    )
    assert lop["loss_of_pay"] == Paise.from_rupees(2000)  # 3/30 of 20000
    assert lop["net_salary"] == full["net_salary"] - Paise.from_rupees(2000)
    # default path is unchanged (no LOP key impact on the figure)
    assert full["loss_of_pay"] == 0


def _seed_employee(session, state="MH"):
    emp = Employee(employee_code="E1", name="Asha", date_of_joining="2021-04-01", state=state)
    session.add(emp)
    session.flush()
    svc = PayrollService()
    svc.set_salary_structure(
        session, emp.id, effective_from="2026-04-01",
        basic=Paise.from_rupees(50000), hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    return svc, emp


def test_lwf_due_totals_for_due_month(session):
    svc, _ = _seed_employee(session, state="MH")
    due = svc.lwf_due(session, period="2026-06")  # June -> MH due month
    assert due["total_employee_paise"] == Paise.from_rupees(25)
    assert due["total_employer_paise"] == Paise.from_rupees(75)
    assert due["by_state"]["MH"]["members"] == 1
    # July -> nothing due
    assert svc.lwf_due(session, period="2026-07")["total_paise"] == 0


def test_run_payroll_with_loss_of_pay(session):
    svc, emp = _seed_employee(session, state="MH")
    full = svc.run_payroll(session, "2026-07", run_date="2026-07-31")
    # 3 unpaid days in a 31-day month -> gross 100000 * 3/31 deducted
    lop = svc.run_payroll(
        session, "2026-07", run_date="2026-07-31", lop_days={emp.id: 3}
    )
    expected_lop = int(s.loss_of_pay(Paise.from_rupees(100000), 3, 31))
    assert lop["total_net"] == full["total_net"] - expected_lop
