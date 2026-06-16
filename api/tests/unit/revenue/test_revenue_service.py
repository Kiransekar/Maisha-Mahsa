from datetime import date

from app.core.money import Paise
from app.db.models.revenue import Customer
from app.db.models.shared import Company
from app.domains.gst.service import GstService
from app.domains.revenue.service import RevenueService

VALID_GSTIN = "27AAPFU0939F1ZV"


def _customer(session, *, state="MH", gstin=None, tds=False):
    c = Customer(
        name="Acme",
        state=state,
        gstin=gstin,
        payment_terms=30,
        tds_applicable=1 if tds else 0,
        tds_rate=10.0 if tds else 0.0,
    )
    session.add(c)
    session.flush()
    return c


def _line(rupees, hsn="9983"):
    return [
        {
            "description": "Service",
            "quantity": 1,
            "rate": Paise.from_rupees(rupees),
            "hsn_code": hsn,
        }
    ]


def test_create_invoice_intra_state_default(session):
    svc = RevenueService()
    cust = _customer(session)
    res = svc.create_invoice(
        session,
        invoice_number="INV-1",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=_line(100000),
        gst_rate=18,
    )
    # no company row -> supplier state unknown -> intra-state
    assert res["cgst_amount"] == Paise.from_rupees(9000)
    assert res["total_amount"] == Paise.from_rupees(118000)
    assert res["due_date"] == "2026-06-09"  # +30 days


def test_create_invoice_inter_state_when_states_differ(session):
    svc = RevenueService()
    session.add(Company(name="Co", pan="AAAAA0000A", state="KA"))
    session.flush()
    cust = _customer(session, state="MH")
    res = svc.create_invoice(
        session,
        invoice_number="INV-2",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=_line(100000),
        gst_rate=18,
    )
    assert res["igst_amount"] == Paise.from_rupees(18000)
    assert res["cgst_amount"] == 0


def test_record_payment_marks_paid(session):
    svc = RevenueService()
    cust = _customer(session)
    res = svc.create_invoice(
        session,
        invoice_number="INV-3",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=_line(100000),
        gst_rate=18,
    )
    svc.record_payment(session, res["invoice_id"], res["net_receivable"], "2026-05-20")
    aging = svc.ar_aging(session, date(2026, 6, 16))
    assert aging["total_outstanding"] == 0


def test_customer_concentration(session):
    svc = RevenueService()
    big = _customer(session, state="MH")
    small = _customer(session, state="MH")
    svc.create_invoice(
        session,
        invoice_number="A",
        customer_id=big.id,
        invoice_date="2026-05-10",
        lines=_line(90000),
        gst_rate=0,
    )
    svc.create_invoice(
        session,
        invoice_number="B",
        customer_id=small.id,
        invoice_date="2026-05-10",
        lines=_line(10000),
        gst_rate=0,
    )
    conc = svc.customer_concentration(session)
    assert conc["ratio"] == 0.9


def test_build_snapshot_flags_missing_irn_and_concentration(session):
    svc = RevenueService()
    cust = _customer(session)
    svc.create_invoice(
        session,
        invoice_number="INV-9",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=_line(100000),
        gst_rate=18,
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    m = snap["metrics"]
    assert m["einvoice_missing"] == 1  # no IRN supplied
    assert m["customer_concentration_ratio"] == 1.0  # single customer
    assert m["annual_turnover_rupees"] == 118000  # ₹1,18,000 incl GST


def test_gstr1_bridge_feeds_gst_module(session):
    """Revenue invoices flow into GST's GSTR-1 builder — closes the cross-module gap."""
    rev = RevenueService()
    session.add(Company(name="Co", pan="AAAAA0000A", state="MH"))
    session.flush()
    cust = _customer(session, state="MH", gstin=VALID_GSTIN)
    rev.create_invoice(
        session,
        invoice_number="INV-7",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=_line(100000),
        gst_rate=18,
    )
    lines = rev.gstr1_lines(session, "2026-05")
    assert len(lines) == 1

    summary = GstService().build_gstr1(lines, filing_period="2026-05")
    assert VALID_GSTIN in summary["b2b"]
    assert summary["totals"]["taxable"] == Paise.from_rupees(100000)
    assert summary["totals"]["total_tax"] == Paise.from_rupees(18000)
    assert summary["errors"] == []  # valid GSTIN + HSN present
