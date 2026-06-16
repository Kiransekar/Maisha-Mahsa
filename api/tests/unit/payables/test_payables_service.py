from datetime import date

from app.core.money import Paise
from app.db.models.payables import PurchaseOrder, Vendor
from app.domains.gst.service import GstService
from app.domains.payables.service import PayablesService


def _vendor(session, *, tds_section=None, msme=False, payee_type="company"):
    v = Vendor(
        name="Vend",
        tds_section=tds_section,
        payee_type=payee_type,
        msme_status=1 if msme else 0,
        payment_terms=30,
    )
    session.add(v)
    session.flush()
    return v


def test_create_bill_deducts_tds(session):
    svc = PayablesService()
    v = _vendor(session, tds_section="194J")
    res = svc.create_bill(
        session,
        bill_number="B1",
        vendor_id=v.id,
        bill_date="2026-05-10",
        subtotal=Paise.from_rupees(50000),
    )
    assert res["tds_amount"] == Paise.from_rupees(5000)  # 10% of 50k
    assert res["total_amount"] == Paise.from_rupees(45000)  # 50k - 5k TDS
    assert res["tds_section"] == "194J"


def test_three_way_match_on_bill(session):
    svc = PayablesService()
    v = _vendor(session)
    po = PurchaseOrder(
        po_number="PO1",
        vendor_id=v.id,
        po_date="2026-05-01",
        total_amount=Paise.from_rupees(100000),
        received_amount=Paise.from_rupees(100000),
    )
    session.add(po)
    session.flush()
    res = svc.create_bill(
        session,
        bill_number="B2",
        vendor_id=v.id,
        bill_date="2026-05-10",
        subtotal=Paise.from_rupees(103000),
        po_id=po.id,
    )
    assert res["three_way_match"]["matched"] is True
    assert res["three_way_match"]["po_variance_pct"] == 3.0


def test_msme_overdue_drives_snapshot(session):
    svc = PayablesService()
    v = _vendor(session, msme=True)
    # bill dated 1 Apr, unpaid at 16 Jun -> 76 days > 45
    svc.create_bill(
        session,
        bill_number="B3",
        vendor_id=v.id,
        bill_date="2026-04-01",
        subtotal=Paise.from_rupees(20000),
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    m = snap["metrics"]
    assert m["msme_max_days_unpaid"] == 76
    assert m["msme_compliance"] == 0.0


def test_match_variance_breach_in_snapshot(session):
    svc = PayablesService()
    v = _vendor(session)
    po = PurchaseOrder(
        po_number="PO9",
        vendor_id=v.id,
        po_date="2026-05-01",
        total_amount=Paise.from_rupees(100000),
        received_amount=Paise.from_rupees(100000),
    )
    session.add(po)
    session.flush()
    svc.create_bill(
        session,
        bill_number="B9",
        vendor_id=v.id,
        bill_date="2026-05-10",
        subtotal=Paise.from_rupees(110000),
        po_id=po.id,
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["max_match_variance_pct"] == 10.0


def test_input_tax_credit_bridge_feeds_gst(session):
    """Payables ITC flows into GST GSTR-3B set-off — closes the input-side gap."""
    pay = PayablesService()
    v = _vendor(session)
    pay.create_bill(
        session,
        bill_number="B-ITC",
        vendor_id=v.id,
        bill_date="2026-05-10",
        subtotal=Paise.from_rupees(100000),
        cgst=Paise.from_rupees(9000),
        sgst=Paise.from_rupees(9000),
    )
    itc = pay.input_tax_credit(session, "2026-05")
    assert itc["cgst"] == Paise.from_rupees(9000)
    assert itc["sgst"] == Paise.from_rupees(9000)

    # feed it into GST: output ₹9k+₹9k fully offset by this ITC -> nil cash
    gst = GstService()
    res = gst.file_gstr3b(
        session,
        filing_period="2026-05",
        due_date="2026-06-20",
        output={"igst": 0, "cgst": Paise.from_rupees(9000), "sgst": Paise.from_rupees(9000)},
        itc_available=itc,
    )
    assert res["cash_total"] == 0
