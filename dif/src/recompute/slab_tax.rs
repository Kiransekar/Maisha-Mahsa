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

#[cfg(test)]
mod tests {
    use super::*;

    // Mirrors api/tests/unit/payroll/test_statutory.py.

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
}
