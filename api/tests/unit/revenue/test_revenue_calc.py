"""Revenue computation checks — invoice GST split, TDS, AR aging, dunning, credit notes."""

from datetime import date

from app.core.money import Paise
from app.domains.revenue import revenue_calc as rc

_LINE = [{"quantity": 1, "rate": Paise.from_rupees(100000)}]  # ₹1,00,000 taxable


def test_intra_state_splits_cgst_sgst():
    comp = rc.compute_invoice(_LINE, gst_rate=18, inter_state=False)
    assert comp["subtotal"] == Paise.from_rupees(100000)
    assert comp["cgst_amount"] == Paise.from_rupees(9000)
    assert comp["sgst_amount"] == Paise.from_rupees(9000)
    assert comp["igst_amount"] == 0
    assert comp["total_amount"] == Paise.from_rupees(118000)
    assert comp["net_receivable"] == Paise.from_rupees(118000)


def test_inter_state_uses_igst():
    comp = rc.compute_invoice(_LINE, gst_rate=18, inter_state=True)
    assert comp["igst_amount"] == Paise.from_rupees(18000)
    assert comp["cgst_amount"] == 0 and comp["sgst_amount"] == 0
    assert comp["total_amount"] == Paise.from_rupees(118000)


def test_tds_deducted_on_taxable_value():
    comp = rc.compute_invoice(_LINE, gst_rate=18, inter_state=False, tds_rate=10)
    # TDS ₹10,000 on ₹1,00,000 taxable; net = total ₹1,18,000 - ₹10,000
    assert comp["tds_amount"] == Paise.from_rupees(10000)
    assert comp["net_receivable"] == Paise.from_rupees(108000)


def test_ar_aging_buckets():
    rec = [
        {"due_date": "2026-06-10", "outstanding_paise": Paise.from_rupees(1000)},  # 6d -> 0-30
        {"due_date": "2026-05-01", "outstanding_paise": Paise.from_rupees(1000)},  # 46d -> 31-60
        {"due_date": "2026-03-01", "outstanding_paise": Paise.from_rupees(1000)},  # 107d -> 90+
        {"due_date": "2026-07-01", "outstanding_paise": Paise.from_rupees(1000)},  # future -> 0-30
        {"due_date": "2026-06-01", "outstanding_paise": 0},  # ignored
    ]
    aging = rc.ar_aging(rec, date(2026, 6, 16))
    assert aging["buckets"]["0-30"] == Paise.from_rupees(2000)
    assert aging["buckets"]["31-60"] == Paise.from_rupees(1000)
    assert aging["buckets"]["90+"] == Paise.from_rupees(1000)
    assert aging["total_outstanding"] == Paise.from_rupees(4000)


def test_dunning_schedule():
    # due 23 Jun, as_of 16 Jun -> 7 days before due -> T-7
    assert rc.dunning_due("2026-06-23", date(2026, 6, 16)) == ["T-7"]
    # due 15 Jun, as_of 16 Jun -> 1 day after due -> T+1
    assert rc.dunning_due("2026-06-15", date(2026, 6, 16)) == ["T+1"]
    assert rc.dunning_due("2026-06-30", date(2026, 6, 16)) == []


def test_credit_note_timeliness_s34():
    # invoice in FY 2025-26 -> CN allowed up to 30 Nov 2026
    assert rc.credit_note_deadline("2025-05-10") == date(2026, 11, 30)
    assert rc.credit_note_deadline("2026-01-10") == date(2026, 11, 30)
    assert rc.is_credit_note_timely("2025-05-10", "2026-11-30") is True
    assert rc.is_credit_note_timely("2025-05-10", "2026-12-01") is False
