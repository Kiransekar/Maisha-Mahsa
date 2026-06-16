from datetime import date

from app.core.money import Paise
from app.db.models.gst import GstReturn, ItcRegister
from app.domains.gst.service import GstService


def test_file_gstr3b_persists_with_late_fee(session):
    svc = GstService()
    res = svc.file_gstr3b(
        session,
        filing_period="2026-05",
        due_date="2026-06-20",
        output={"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
        filed_date="2026-06-25",  # 5 days late
    )
    assert res["cash_total"] == Paise.from_rupees(10000)
    assert res["late_fee"] == Paise.from_rupees(250)
    ret = session.get(GstReturn, res["gst_return_id"])
    assert ret.status == "filed"
    assert ret.tax_payable == Paise.from_rupees(10000)


def test_reconcile_itc_ratio(session):
    svc = GstService()
    session.add(
        ItcRegister(
            gstin_supplier="27AAPFU0939F1ZV",
            invoice_number="A1",
            invoice_date="2026-05-02",
            taxable_value=Paise.from_rupees(1000),
            total_tax=Paise.from_rupees(100),
            eligible_itc=1,
            in_2b=1,
        )
    )
    session.add(
        ItcRegister(
            gstin_supplier="27AAPFU0939F1ZV",
            invoice_number="A2",
            invoice_date="2026-05-03",
            taxable_value=Paise.from_rupees(200),
            total_tax=Paise.from_rupees(20),
            eligible_itc=1,
            in_2b=0,  # claimed but not in 2B
        )
    )
    session.flush()
    recon = svc.reconcile_itc(session)
    assert recon["available_2b_paise"] == Paise.from_rupees(100)
    assert recon["claimed_paise"] == Paise.from_rupees(120)
    assert recon["itc_claimed_ratio"] == 1.2
    assert recon["gap_paise"] == Paise.from_rupees(20)


def test_build_snapshot_flags_overdue_unfiled_return(session):
    svc = GstService()
    # an unfiled GSTR-3B due before as_of -> overdue
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-04",
            due_date="2026-05-20",
            status="pending",
        )
    )
    session.flush()
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    m = snap["metrics"]
    assert m["gstr3b_days_late"] == 27  # 20 May -> 16 Jun
    assert m["filing_timeliness"] == 0.0
    assert m["penalty_exposure"] == 0.0


def test_build_snapshot_clean_when_filed_on_time(session):
    svc = GstService()
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-04",
            due_date="2026-05-20",
            filed_date="2026-05-18",
            status="filed",
        )
    )
    session.flush()
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["gstr3b_days_late"] == 0
    assert snap["metrics"]["filing_timeliness"] == 1.0
