from datetime import date

import pytest
from sqlalchemy import select

from app.core.money import Paise
from app.db.models.payroll import Employee, PayrollEntry
from app.domains.payroll.service import PayrollService, check_ctc_compliance, compute_components


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


def test_ctc_compliance_ok_basic_at_least_half():
    # basic 60k of a 100k total (>= 50%) -> compliant, no suggestion
    report = check_ctc_compliance(
        basic=Paise.from_rupees(60000),
        hra=Paise.from_rupees(30000),
        special_allowance=Paise.from_rupees(10000),
    )
    assert report["compliant"] is True
    assert report["status"] == "ok"
    assert report["suggestion"] is None


def test_ctc_compliance_warns_and_proposes_rebalance_below_half():
    # basic 10k of a 30k total (1/3 < 50%) -> non-compliant; rebalance raises basic to 15k,
    # funded first from special_allowance (0 -> takes 0), then LTA (0), then HRA (20k -> 15k)
    report = check_ctc_compliance(
        basic=Paise.from_rupees(10000),
        hra=Paise.from_rupees(20000),
    )
    assert report["compliant"] is False
    assert report["status"] == "non_compliant"
    assert report["total_remuneration"] == Paise.from_rupees(30000)
    assert report["required_minimum_basic_plus_da"] == Paise.from_rupees(15000)
    suggestion = report["suggestion"]
    assert suggestion is not None
    assert suggestion["basic"] == Paise.from_rupees(15000)
    assert suggestion["hra"] == Paise.from_rupees(15000)
    assert suggestion["lta"] == 0
    assert suggestion["special_allowance"] == 0
    # total CTC (these 4 components) held exactly constant
    assert sum(suggestion.values()) == Paise.from_rupees(30000)


def test_ctc_compliance_rebalance_trims_special_allowance_before_hra_lta():
    report = check_ctc_compliance(
        basic=Paise.from_rupees(10000),
        hra=Paise.from_rupees(5000),
        lta=Paise.from_rupees(5000),
        special_allowance=Paise.from_rupees(10000),
    )
    assert report["compliant"] is False
    suggestion = report["suggestion"]
    assert suggestion["basic"] == Paise.from_rupees(15000)
    assert suggestion["special_allowance"] == Paise.from_rupees(5000)  # trimmed first
    assert suggestion["hra"] == Paise.from_rupees(5000)  # untouched
    assert suggestion["lta"] == Paise.from_rupees(5000)  # untouched
    assert sum(suggestion.values()) == Paise.from_rupees(30000)


def test_ctc_compliance_zero_total_is_compliant_no_division_by_zero():
    report = check_ctc_compliance(basic=0, hra=0)
    assert report["compliant"] is True
    assert report["suggestion"] is None


def test_ctc_compliance_rounding_uses_ceiling_for_required_minimum():
    # total = 100001 paise (odd); exact half = 50000.5 -> required minimum ceils to 50001,
    # so basic=50000 is one paise short and must be flagged non-compliant.
    report = check_ctc_compliance(basic=50000, hra=50001)
    assert report["compliant"] is False
    assert report["required_minimum_basic_plus_da"] == 50001
    assert report["suggestion"]["basic"] == 50001
    assert report["suggestion"]["hra"] == 50000
    assert sum(report["suggestion"].values()) == 100001


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


def test_validate_ctc_service_reports_warning_and_never_mutates_stored_structure(session):
    # service-level integration: a real persisted structure with basic under-weighted below
    # the s.2(y) 50% floor (basic 10k of a 30k gross) must be flagged, with a suggestion —
    # and the stored row must come back byte-identical afterwards (never silently altered).
    svc = PayrollService()
    emp = _employee(session)
    structure = svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(10000),
        hra=Paise.from_rupees(20000),
    )
    before = (structure.basic, structure.hra, structure.lta, structure.special_allowance)

    report = svc.validate_ctc(session, emp.id, on_or_before="2026-06-01")

    assert report["compliant"] is False
    assert report["status"] == "non_compliant"
    assert report["suggestion"]["basic"] == Paise.from_rupees(15000)

    after = (structure.basic, structure.hra, structure.lta, structure.special_allowance)
    assert after == before  # read-only: nothing was written back


def test_validate_ctc_service_ok_for_compliant_structure(session):
    svc = PayrollService()
    emp = _employee(session)
    svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(60000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(20000),
    )
    report = svc.validate_ctc(session, emp.id, on_or_before="2026-06-01")
    assert report["compliant"] is True
    assert report["suggestion"] is None


def test_validate_ctc_raises_for_employee_without_a_structure(session):
    svc = PayrollService()
    emp = _employee(session)
    with pytest.raises(ValueError, match="no salary structure"):
        svc.validate_ctc(session, emp.id, on_or_before="2026-06-01")
