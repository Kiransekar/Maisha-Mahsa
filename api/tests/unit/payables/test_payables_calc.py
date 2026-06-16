"""Payables computation checks — TDS section engine, 3-way match, AP aging."""

from datetime import date

from app.core.money import Paise
from app.domains.payables import payables_calc as p


# ---- TDS ----
def test_194j_professional_above_threshold():
    res = p.tds_on_payment("194J", Paise.from_rupees(50000))
    assert res["applicable"] is True
    assert res["tds_paise"] == Paise.from_rupees(5000)  # 10%


def test_194j_below_threshold_no_tds():
    res = p.tds_on_payment("194J", Paise.from_rupees(20000))
    assert res["applicable"] is False
    assert res["tds_paise"] == 0


def test_194c_rate_depends_on_payee_type():
    company = p.tds_on_payment("194C", Paise.from_rupees(40000), payee_type="company")
    individual = p.tds_on_payment("194C", Paise.from_rupees(40000), payee_type="individual")
    assert company["tds_paise"] == Paise.from_rupees(800)  # 2%
    assert individual["tds_paise"] == Paise.from_rupees(400)  # 1%


def test_194c_aggregate_threshold_triggers_tds():
    # single ₹20k < ₹30k, but YTD ₹90k + ₹20k = ₹1.1L >= ₹1L aggregate -> TDS applies
    res = p.tds_on_payment(
        "194C",
        Paise.from_rupees(20000),
        payee_type="company",
        aggregate_ytd=Paise.from_rupees(90000),
    )
    assert res["applicable"] is True
    assert res["tds_paise"] == Paise.from_rupees(400)  # 2% of 20k


def test_194h_and_194i_rates():
    assert p.tds_on_payment("194H", Paise.from_rupees(25000))["tds_paise"] == Paise.from_rupees(500)
    plant = p.tds_on_payment("194I", Paise.from_rupees(300000), category="plant")
    building = p.tds_on_payment("194I", Paise.from_rupees(300000), category="building")
    assert plant["tds_paise"] == Paise.from_rupees(6000)  # 2%
    assert building["tds_paise"] == Paise.from_rupees(30000)  # 10%


# ---- 3-way match ----
def test_three_way_match_within_tolerance():
    m = p.three_way_match(
        Paise.from_rupees(100000),
        Paise.from_rupees(103000),
        grn_amount=Paise.from_rupees(100000),
    )
    assert m["matched"] is True
    assert m["po_variance_pct"] == 3.0


def test_three_way_match_breaches_tolerance():
    m = p.three_way_match(Paise.from_rupees(100000), Paise.from_rupees(110000))
    assert m["matched"] is False
    assert m["max_variance_pct"] == 10.0


# ---- AP aging ----
def test_ap_aging_buckets():
    payables = [
        {"due_date": "2026-06-10", "outstanding_paise": Paise.from_rupees(1000)},  # 0-30
        {"due_date": "2026-03-01", "outstanding_paise": Paise.from_rupees(1000)},  # 90+
    ]
    aging = p.ap_aging(payables, date(2026, 6, 16))
    assert aging["buckets"]["0-30"] == Paise.from_rupees(1000)
    assert aging["buckets"]["90+"] == Paise.from_rupees(1000)
    assert aging["total_outstanding"] == Paise.from_rupees(2000)
