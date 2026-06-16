"""Direct-tax computation checks — 234C interest, 234E late fee, 44AB trigger, MAT.
Every expected value is worked out in the comment."""

from app.core.money import Paise
from app.domains.tax import tax_calc as t


def test_234c_full_shortfall():
    # liability ₹4,00,000, nothing paid:
    # Q1 60k×1%×3=1,800 ; Q2 1.8L×1%×3=5,400 ; Q3 3L×1%×3=9,000 ; Q4 4L×1%×1=4,000 = ₹20,200
    res = t.interest_234c(Paise.from_rupees(400000), [0, 0, 0, 0])
    assert res["total_234c"] == Paise.from_rupees(20200)
    assert res["by_installment"]["Q3"] == Paise.from_rupees(9000)


def test_234c_no_interest_when_on_schedule():
    paid = [Paise.from_rupees(x) for x in (60000, 180000, 300000, 400000)]
    assert t.interest_234c(Paise.from_rupees(400000), paid)["total_234c"] == 0


def test_234c_q1_relief_below_15pct():
    # ₹50k paid by Q1 (< ₹60k required) but >= ₹48k (12%) -> no Q1 interest
    paid = [Paise.from_rupees(x) for x in (50000, 180000, 300000, 400000)]
    res = t.interest_234c(Paise.from_rupees(400000), paid)
    assert res["by_installment"]["Q1"] == 0
    assert res["total_234c"] == 0


def test_234e_late_fee_and_cap():
    assert t.late_fee_234e(10, Paise.from_rupees(50000)) == Paise.from_rupees(2000)  # ₹200×10
    # capped at the TDS amount:
    assert t.late_fee_234e(1000, Paise.from_rupees(5000)) == Paise.from_rupees(5000)
    assert t.late_fee_234e(0, Paise.from_rupees(50000)) == 0


def test_44ab_audit_trigger():
    assert t.audit_required(Paise.from_rupees(15000000), cash_ratio=0.10) is True  # >₹1Cr, cash>5%
    assert t.audit_required(Paise.from_rupees(15000000), cash_ratio=0.02) is False  # mostly digital
    assert t.audit_required(Paise.from_rupees(120000000)) is True  # >₹10Cr always
    assert t.audit_required(Paise.from_rupees(6000000), is_professional=True) is True  # >₹50L


def test_mat_liability():
    # ₹10,00,000 book profit × 15% × 1.04 cess = ₹1,56,000
    assert t.mat_liability(Paise.from_rupees(1000000)) == Paise.from_rupees(156000)
    assert t.mat_liability(0) == 0
