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


def test_gratuity_required_ceiling_pair():
    # CoSS 2020 s.53(3) notified ceiling ₹20,00,000 (S.O. 1420(E) via s.164(2)(a) — see
    # ws1b_wiring_gratuity.yaml). PAIRED: under the cap passes through, over it clamps exactly.
    # ₹2,00,000 × 17y = ₹19,61,538 (< cap, untouched); × 18y raw ₹20,76,923 -> exactly ₹20,00,000.
    assert s.gratuity_required(Paise.from_rupees(200000), 17) == Paise.from_rupees(1961538)
    assert s.gratuity_required(Paise.from_rupees(200000), 18) == int(s.GRATUITY_CEILING)


def test_gratuity_hybrid_eligibility_pairs():
    # CoSS 2020 s.53(1): five-year floor, PAIRED at the boundary; the one-year floor is the
    # statute's own FIXED-TERM exception (second proviso + MoLE FAQ Sl.14), not the rule.
    from datetime import date as d

    kw = dict(boundary=d(2025, 11, 21), old_base=0, new_base=Paise.from_rupees(26000))
    # exactly 5 completed years -> payable ₹75,000; one day short (4 years) -> nil (non-FTE)
    assert s.gratuity_hybrid(doj=d(2026, 1, 1), exit_date=d(2031, 1, 1), **kw) == Paise.from_rupees(
        75000
    )
    assert s.gratuity_hybrid(doj=d(2026, 1, 1), exit_date=d(2030, 12, 31), **kw) == 0
    # FTE: exactly 1 year -> ₹15,000; 11 months -> nil; 2y non-FTE nil vs 2y FTE ₹30,000
    assert s.gratuity_hybrid(
        doj=d(2026, 1, 1), exit_date=d(2027, 1, 1), fixed_term=True, **kw
    ) == Paise.from_rupees(15000)
    assert (
        s.gratuity_hybrid(doj=d(2026, 1, 1), exit_date=d(2026, 12, 1), fixed_term=True, **kw) == 0
    )
    assert s.gratuity_hybrid(doj=d(2026, 1, 1), exit_date=d(2028, 1, 1), **kw) == 0
    assert s.gratuity_hybrid(
        doj=d(2026, 1, 1), exit_date=d(2028, 1, 1), fixed_term=True, **kw
    ) == Paise.from_rupees(30000)


def test_bonus_provision():
    # basic ₹6,000 -> 1/12 = ₹500.00 exact
    assert s.bonus_provision_monthly(Paise.from_rupees(6000)) == Paise.from_rupees(500)
    # basic ₹10,000 -> capped at ₹7,000 -> 700000/12 = ₹583.33 -> ₹583
    assert s.bonus_provision_monthly(Paise.from_rupees(10000)) == Paise.from_rupees(583)
    # basic ₹25,000 -> above eligibility -> nil
    assert s.bonus_provision_monthly(Paise.from_rupees(25000)) == 0


def test_bonus_rate_is_exactly_one_twelfth():
    # D1 fix pinned: CoW 2019 s.26(1) "eight and one-third per cent." = 1/12 exactly.
    # Basic ₹6,006 -> 600600/12 = ₹500.50 -> half-up ₹501 (the old 0.0833 gave ₹500).
    assert s.bonus_provision_monthly(Paise.from_rupees(6006)) == Paise.from_rupees(501)


def test_bonus_annual_100_floor():
    # D2 fix pinned: s.26(1) "or one hundred rupees, whichever is higher" — ANNUAL floor.
    # Basic ₹60/month: rate leg ₹5/month; floor slice 10000/12 = ₹8.33 -> ₹8.
    assert s.bonus_provision_monthly(Paise.from_rupees(60)) == Paise.from_rupees(8)
    # At exactly ₹100/month the legs coincide (both 10000/12 -> ₹8); above, the rate leg rules.
    assert s.bonus_provision_monthly(Paise.from_rupees(100)) == Paise.from_rupees(8)


def test_surcharge_bands_and_marginal_relief():
    # FA 2025 s.2(9) new-regime bands: 10% >50L, 15% >1cr, 25% >2cr, with marginal relief.
    assert s.annual_income_tax(Paise.from_rupees(5000000)) == Paise.from_rupees(1123200)
    assert s.annual_income_tax(500_000_100) == Paise.from_rupees(1123201)  # ₹50L + ₹1: relief
    assert s.annual_income_tax(Paise.from_rupees(5200000)) == Paise.from_rupees(1304160)
    assert s.annual_income_tax(Paise.from_rupees(10000000)) == Paise.from_rupees(2951520)
    assert s.annual_income_tax(1_000_000_100) == Paise.from_rupees(2951521)  # ₹1cr + ₹1: relief
    assert s.annual_income_tax(Paise.from_rupees(20000000)) == Paise.from_rupees(6673680)
    assert s.annual_income_tax(2_000_000_100) == Paise.from_rupees(6673681)  # ₹2cr + ₹1: relief
    assert s.annual_income_tax(Paise.from_rupees(30000000)) == Paise.from_rupees(11154000)
