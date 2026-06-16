from datetime import date

from app.domains.compliance.service import ComplianceService


def test_seed_month_creates_standard_deadlines(session):
    svc = ComplianceService()
    ids = svc.seed_month(session, "2026-05")  # liabilities of May, due in June
    assert len(ids) == 5  # tds, pf, esi, gst, pt
    # GSTR-3B for May is due 20 June
    alerts = svc.alerts(session, date(2026, 6, 20))
    gst = [a for a in alerts if a["domain"] == "gst"]
    assert gst and gst[0]["label"] == "T-0"


def test_build_snapshot_overdue_drives_metrics(session):
    svc = ComplianceService()
    svc.add_deadline(
        session,
        domain="gst",
        form_name="GSTR-3B (Apr)",
        due_date="2026-05-20",
        filing_period="2026-04",
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["overdue_filings"] == 1
    assert snap["metrics"]["gst_filing_status"] == 0.0
    assert snap["metrics"]["tds_filing_status"] == 1.0  # nothing overdue


def test_mark_filed_clears_overdue(session):
    svc = ComplianceService()
    did = svc.add_deadline(
        session,
        domain="gst",
        form_name="GSTR-3B (Apr)",
        due_date="2026-05-20",
    )
    svc.mark_filed(session, did, filed_date="2026-05-19", acknowledgement="ACK123")
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["overdue_filings"] == 0
    assert snap["metrics"]["gst_filing_status"] == 1.0
