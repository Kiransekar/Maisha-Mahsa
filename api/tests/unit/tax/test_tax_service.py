from datetime import date

from app.core.money import Paise
from app.db.models.payables import Bill, Vendor
from app.db.models.payroll import PayrollEntry, PayrollRun
from app.db.models.tax import TdsEntry
from app.domains.tax.service import TaxService


def test_file_tds_return_late_fee(session):
    svc = TaxService()
    res = svc.file_tds_return(
        session,
        return_type="26Q",
        quarter="2026-Q1",
        due_date="2026-07-31",
        total_deducted=Paise.from_rupees(50000),
        filed_date="2026-08-10",  # 10 days late
    )
    assert res["late_filing_fee"] == Paise.from_rupees(2000)
    assert res["status"] == "filed"


def test_tds_deducted_summary_bridges_payroll_and_payables(session):
    svc = TaxService()
    run = PayrollRun(month_year="2026-06", run_date="2026-06-30")
    session.add(run)
    session.flush()
    session.add(
        PayrollEntry(
            payroll_run_id=run.id,
            employee_id=1,
            gross=Paise.from_rupees(150000),
            basic=Paise.from_rupees(75000),
            hra=Paise.from_rupees(30000),
            employee_pf=Paise.from_rupees(1800),
            net_pay=Paise.from_rupees(135000),
            tds=Paise.from_rupees(12567),
        )
    )
    vendor = Vendor(name="V", payment_terms=30)
    session.add(vendor)
    session.flush()
    session.add(
        Bill(
            bill_number="B1",
            vendor_id=vendor.id,
            bill_date="2026-06-10",
            due_date="2026-07-10",
            subtotal=Paise.from_rupees(50000),
            total_amount=Paise.from_rupees(45000),
            tds_amount=Paise.from_rupees(5000),
        )
    )
    session.flush()

    summary = svc.tds_deducted_summary(session, "2026-06")
    assert summary["payroll_tds"] == Paise.from_rupees(12567)
    assert summary["payables_tds"] == Paise.from_rupees(5000)
    assert summary["total"] == Paise.from_rupees(17567)


def test_advance_tax_interest_from_records(session):
    svc = TaxService()
    # no installments recorded -> full 234C shortfall for ₹4,00,000 liability = ₹20,200
    res = svc.advance_tax_interest(session, fy="2026-27", total_liability=Paise.from_rupees(400000))
    assert res["total_234c"] == Paise.from_rupees(20200)


def test_build_snapshot_flags_overdue_tds_deposit(session):
    svc = TaxService()
    # TDS deducted on 10 Apr -> due 7 May -> unpaid at 16 Jun -> overdue
    session.add(
        TdsEntry(
            deductee_name="X",
            section="194J",
            payment_date="2026-04-10",
            payment_amount=Paise.from_rupees(50000),
            tds_amount=Paise.from_rupees(5000),
            total_tds=Paise.from_rupees(5000),
        )
    )
    session.flush()
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    m = snap["metrics"]
    assert m["tds_days_overdue"] == 40  # 7 May -> 16 Jun
    assert m["tds_deposit_timeliness"] == 0.0
