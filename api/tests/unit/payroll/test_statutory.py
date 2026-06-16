"""Hand-computed statutory checks (FY 2025-26, new regime). Every expected value is worked
out in the comment so a CA can verify it independently."""

from app.core.money import Paise
from app.domains.payroll import statutory as s


# ---- PF ----
def test_pf_capped_at_ceiling():
    # basic ₹50,000 -> PF wage capped at ₹15,000 -> 12% = ₹1,800
    assert s.pf_employee(Paise.from_rupees(50000)) == Paise.from_rupees(1800)
    assert s.pf_employer(Paise.from_rupees(50000)) == Paise.from_rupees(1800)


def test_pf_below_ceiling_uses_actual_basic():
    # basic ₹10,000 -> 12% = ₹1,200
    assert s.pf_employee(Paise.from_rupees(10000)) == Paise.from_rupees(1200)


# ---- ESI ----
def test_esi_applies_below_ceiling_and_rounds_up():
    # gross ₹15,000: employee 0.75% = ₹112.50 -> ceil ₹113; employer 3.25% = ₹487.50 -> ceil ₹488
    emp, empr = s.esi(Paise.from_rupees(15000))
    assert emp == Paise.from_rupees(113)
    assert empr == Paise.from_rupees(488)


def test_esi_nil_above_ceiling():
    emp, empr = s.esi(Paise.from_rupees(25000))
    assert emp == 0 and empr == 0


# ---- Professional Tax ----
def test_pt_maharashtra_slabs_and_february_special():
    assert s.professional_tax("MH", Paise.from_rupees(7000), 6) == 0
    assert s.professional_tax("MH", Paise.from_rupees(9000), 6) == Paise.from_rupees(175)
    assert s.professional_tax("MH", Paise.from_rupees(20000), 6) == Paise.from_rupees(200)
    assert s.professional_tax("MH", Paise.from_rupees(20000), 2) == Paise.from_rupees(300)


def test_pt_karnataka_and_unmodelled_state():
    assert s.professional_tax("KA", Paise.from_rupees(20000), 6) == 0
    assert s.professional_tax("KA", Paise.from_rupees(30000), 6) == Paise.from_rupees(200)
    assert s.professional_tax("TN", Paise.from_rupees(50000), 6) == 0  # not modelled -> 0
    assert s.professional_tax(None, Paise.from_rupees(50000), 6) == 0


# ---- TDS (s.192 new regime) ----
def test_tds_zero_under_rebate_limit():
    # taxable ₹12,00,000 -> s.87A rebate -> nil
    assert s.annual_income_tax(Paise.from_rupees(1200000)) == 0


def test_tds_marginal_relief_just_above_rebate_limit():
    # taxable ₹12,10,000: slab tax ₹61,500, but capped at the ₹10,000 excess by marginal
    # relief, +4% cess = ₹10,400
    assert s.annual_income_tax(Paise.from_rupees(1210000)) == Paise.from_rupees(10400)


def test_tds_high_income_with_cess():
    # taxable ₹17,25,000: slab tax ₹1,45,000 + 4% cess = ₹1,50,800
    assert s.annual_income_tax(Paise.from_rupees(1725000)) == Paise.from_rupees(150800)


def test_monthly_tds_projection():
    # gross ₹18,00,000 - ₹75,000 std ded = ₹17,25,000 taxable -> ₹1,50,800 / 12 = ₹12,567
    assert s.monthly_tds(Paise.from_rupees(1800000)) == Paise.from_rupees(12567)


def test_monthly_tds_nil_for_modest_salary():
    # gross ₹12,00,000 - ₹75,000 = ₹11,25,000 taxable < ₹12,00,000 -> nil
    assert s.monthly_tds(Paise.from_rupees(1200000)) == 0


# ---- Gratuity & Bonus ----
def test_gratuity_formula():
    # (15/26) × ₹26,000 × 5 years = ₹75,000
    assert s.gratuity_required(Paise.from_rupees(26000), 5) == Paise.from_rupees(75000)
    assert s.gratuity_required(Paise.from_rupees(26000), 0) == 0


def test_bonus_provision():
    # basic ₹6,000 -> 8.33% = ₹499.80 -> ₹500
    assert s.bonus_provision_monthly(Paise.from_rupees(6000)) == Paise.from_rupees(500)
    # basic ₹10,000 -> capped at ₹7,000 -> 8.33% = ₹583.10 -> ₹583
    assert s.bonus_provision_monthly(Paise.from_rupees(10000)) == Paise.from_rupees(583)
    # basic ₹25,000 -> above eligibility -> nil
    assert s.bonus_provision_monthly(Paise.from_rupees(25000)) == 0
