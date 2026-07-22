//! Individual slab tax + cess, s.87A rebate and marginal relief (mirror of
//! app/domains/payroll/statutory.py::annual_income_tax, new regime FY 2025-26). §WS3.1.
use crate::money::Paise;

/// New-regime annual slabs FY 2025-26: (lower_paise, upper_paise_or_None, rate_percent).
/// Bounds are rupees × 100 (paise); mirror of `_TDS_SLABS`.
const SLABS: [(i64, Option<i64>, i64); 7] = [
    (0, Some(40_000_000), 0),
    (40_000_000, Some(80_000_000), 5),
    (80_000_000, Some(120_000_000), 10),
    (120_000_000, Some(160_000_000), 15),
    (160_000_000, Some(200_000_000), 20),
    (200_000_000, Some(240_000_000), 25),
    (240_000_000, None, 30),
];

/// s.87A: taxable ≤ ₹12,00,000 → nil tax (mirror of `REBATE_LIMIT`).
const REBATE_LIMIT: i64 = 120_000_000;

/// Slab tax in paise, mirror of Python `_slab_tax`. Rates are percent, so the exact rational
/// is `Σ (top-lower)·pct / 100`; we sum the integer hundredths and divide ONCE (Python sums
/// Decimals then `int()`-truncates once — identical for non-negative sums).
fn slab_tax(taxable: i64) -> i64 {
    let mut hundredths = 0i64;
    for (lower, upper, pct) in SLABS {
        if taxable <= lower {
            break;
        }
        let top = match upper {
            None => taxable,
            Some(u) => taxable.min(u),
        };
        if top > lower {
            hundredths += (top - lower) * pct;
        }
    }
    hundredths / 100
}

/// Annual income tax incl. 4% cess, after s.87A rebate and marginal relief. Input & output paise.
pub fn annual_income_tax(annual_taxable: i64) -> Paise {
    if annual_taxable <= 0 {
        return Paise(0);
    }
    let mut base = slab_tax(annual_taxable);
    if annual_taxable <= REBATE_LIMIT {
        base = 0;
    } else {
        // marginal relief: tax cannot exceed income above the rebate limit.
        base = base.min(annual_taxable - REBATE_LIMIT);
    }
    // 4% cess, rounded half-up: exact base·1.04 = base·104/100, then round to nearest paise.
    let with_cess = (base * 104 + 50) / 100;
    Paise(crate::recompute::round_rupee(with_cess))
}

/// s.234E late fee for a TDS return: ₹200/day (20000 paise), capped at the TDS amount. Nil if
/// not late. Mirror of app/domains/tax/tax_calc.py::late_fee_234e. Integer paise, exact.
pub fn late_fee_234e(days_late: i64, tds_amount: i64) -> i64 {
    if days_late <= 0 {
        return 0;
    }
    (20_000 * days_late).min(tds_amount)
}

/// s.234B interest (paise): 1%/month on the shortfall when advance tax < 90% of assessed tax,
/// the shortfall rounded DOWN to the nearest ₹100 (Rule 119A(c), Income-tax Rules 1962).
/// Mirror of tax_calc.py::interest_234b
/// (returns just the interest figure). Exact integer paise.
pub fn interest_234b(assessed_tax: i64, advance_paid: i64, months: i64) -> i64 {
    if assessed_tax <= 0 || months <= 0 {
        return 0;
    }
    // advance_paid >= 90% of assessed_tax → no interest (10·advance >= 9·assessed, no floats).
    if advance_paid * 10 >= assessed_tax * 9 {
        return 0;
    }
    let mut shortfall = (assessed_tax - advance_paid).max(0);
    shortfall = (shortfall / 10_000) * 10_000; // round down to the nearest ₹100 (10,000 paise)
    // interest = round_rupee(shortfall · 1% · months); shortfall is a whole-₹100 amount so
    // shortfall/100·months is already whole rupees.
    crate::recompute::round_rupee(shortfall / 100 * months)
}

// s.234C deferment schedule: (cumulative-required %, relief-floor %, deferment months) ×100.
const ADVANCE_TAX_SCHEDULE: [(i64, i64, i64); 4] =
    [(15, 12, 3), (45, 36, 3), (75, 75, 3), (100, 100, 1)];

/// s.234C total deferment interest (paise) given cumulative advance tax paid by each of the 4 due
/// dates. No interest for an installment whose paid amount reaches the relief floor. Mirror of
/// tax_calc.py::interest_234c (returns just `total_234c`). Exact integer paise.
pub fn interest_234c(total_liability: i64, cumulative_paid: &[i64]) -> i64 {
    let mut total = 0i64;
    for (i, &(pct, floor, months)) in ADVANCE_TAX_SCHEDULE.iter().enumerate() {
        let paid = cumulative_paid.get(i).copied().unwrap_or(0);
        // paid >= floor·total ⇔ paid·100 >= total·floor (floor is a /100 percent).
        if paid * 100 >= total_liability * floor {
            continue;
        }
        // interest = round_rupee((total·pct/100 − paid)·1%·months). Numerator N below is
        // (total·pct − paid·100)·months = shortfall_paise·100·months; round half-up to the rupee.
        let n =
            (total_liability as i128 * pct as i128 - paid as i128 * 100) * months as i128;
        if n <= 0 {
            continue;
        }
        let rupees = ((n + 500_000) / 1_000_000) as i64; // half-up of N/1_000_000
        total += rupees * 100;
    }
    total
}

/// s.115BAA company tax (paise): 22% base × 1.10 surcharge × 1.04 cess = 25.168% effective, MAT
/// excluded (§WS1.C4). ``total_income`` = gross total income − deductions. Mirror of the company
/// path of tax_calc.py::itr_computation (its ``normal_tax``). Exact integer paise.
pub fn company_tax_115baa(total_income: i64) -> i64 {
    if total_income <= 0 {
        return 0;
    }
    // effective 0.251680; round_rupee(total·251680/1_000_000). N/1e8 = rupees, half-up.
    let n = total_income as i128 * 251_680;
    (((n + 50_000_000) / 100_000_000) as i64) * 100
}

#[cfg(test)]
mod tests {
    use super::*;

    // Mirrors api/tests/unit/payroll/test_statutory.py.

    #[test]
    fn late_fee_234e_and_cap() {
        // Mirrors api/tests/unit/tax/test_tax_calc.py::test_234e_late_fee_and_cap.
        assert_eq!(late_fee_234e(10, 5_000_000), 200_000); // ₹200×10 = ₹2,000
        assert_eq!(late_fee_234e(1000, 500_000), 500_000); // capped at the TDS amount
        assert_eq!(late_fee_234e(0, 5_000_000), 0); // not late
    }

    #[test]
    fn zero_and_negative_taxable() {
        assert_eq!(annual_income_tax(0), Paise(0));
        assert_eq!(annual_income_tax(-5000), Paise(0));
    }

    #[test]
    fn tds_zero_under_rebate_limit() {
        // taxable ₹12,00,000 -> s.87A rebate -> nil
        assert_eq!(annual_income_tax(120_000_000), Paise(0));
    }

    #[test]
    fn tds_marginal_relief_just_above_rebate_limit() {
        // taxable ₹12,10,000: slab tax ₹61,500 capped at ₹10,000 excess, +4% cess = ₹10,400
        assert_eq!(annual_income_tax(121_000_000), Paise(1_040_000));
    }

    #[test]
    fn tds_high_income_with_cess() {
        // taxable ₹17,25,000: slab tax ₹1,45,000 + 4% cess = ₹1,50,800
        assert_eq!(annual_income_tax(172_500_000), Paise(15_080_000));
    }

    #[test]
    fn i234b_applies_and_relief() {
        // assessed ₹5L, advance ₹1L (< 90%=₹4.5L), 5 months: shortfall ₹4L × 1% × 5 = ₹20,000.
        assert_eq!(interest_234b(50_000_000, 10_000_000, 5), 2_000_000);
        // advance >= 90% of assessed -> no interest.
        assert_eq!(interest_234b(50_000_000, 45_000_000, 5), 0);
        assert_eq!(interest_234b(0, 0, 5), 0);
    }

    #[test]
    fn i234b_rule_119a_rounding_exercised() {
        // Mirrors test_interest_234b.py::test_shortfall_rounded_down_to_hundred. The raw
        // shortfall ₹1,00,050 is NOT a ₹100 multiple — Rule 119A(c) rounds the interest base
        // DOWN to ₹1,00,000; a prior test used an input already on the boundary, leaving the
        // rounding line unlocked (deleting it stayed green). ₹1,00,000 × 1% × 1 = ₹1,000.
        assert_eq!(interest_234b(10_005_000, 0, 1), 100_000);
        // Paired: shortfall exactly on the ₹100 boundary passes through unchanged.
        assert_eq!(interest_234b(10_005_000, 5_000, 1), 100_000);
    }

    #[test]
    fn i234c_full_shortfall_matches_python() {
        // total ₹4,00,000, nothing paid -> ₹1800+₹5400+₹9000+₹4000 = ₹20,200 (tax_calc test).
        assert_eq!(interest_234c(40_000_000, &[0, 0, 0, 0]), 2_020_000);
        // fully on schedule -> nil.
        assert_eq!(
            interest_234c(40_000_000, &[6_000_000, 18_000_000, 30_000_000, 40_000_000]),
            0
        );
    }

    #[test]
    fn i115baa_effective_rate() {
        // ₹1,00,00,000 income × 25.168% = ₹25,16,800 (§WS1.C4).
        assert_eq!(company_tax_115baa(1_000_000_000), 251_680_000);
        assert_eq!(company_tax_115baa(0), 0);
    }
}
