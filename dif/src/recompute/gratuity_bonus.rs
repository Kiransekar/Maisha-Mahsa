//! Gratuity (incl. the §WS1.B2 hybrid transition) + statutory minimum bonus (mirror of
//! app/domains/payroll/statutory.py). §WS3.1. All amounts integer paise; dates injected.
use crate::money::Paise;
use crate::recompute::round_rupee;

/// A calendar date as (year, month, day) — dates are injected, no clock, no chrono dependency.
pub type Ymd = (i32, u32, u32);

/// Whole completed years of service (anniversary count), mirror of Python `_completed_years`.
fn completed_years(doj: Ymd, exit_date: Ymd) -> i64 {
    let mut y = (exit_date.0 - doj.0) as i64;
    if (exit_date.1, exit_date.2) < (doj.1, doj.2) {
        y -= 1;
    }
    y.max(0)
}

/// Hybrid gratuity across the 2025-11-21 Labour-Code transition (§WS1.B2). Completed years whose
/// anniversary falls strictly before `boundary` are valued on `old_base`, the rest on `new_base`;
/// both legs use 15/26; FTE eligibility nil under 1 completed year. Mirror the Python rounding
/// EXACTLY: round the fractional-paise sum half-up to whole paise, THEN half-up to whole rupee.
pub fn gratuity_hybrid(
    doj: Ymd,
    exit_date: Ymd,
    boundary: Ymd,
    old_base: i64,
    new_base: i64,
) -> Paise {
    let total = completed_years(doj, exit_date);
    if total < 1 {
        return Paise(0);
    }
    let pre = (1..=total)
        .filter(|&k| (doj.0 + k as i32, doj.1, doj.2) < boundary)
        .count() as i64;
    let post = total - pre;
    // Sum the two exact rationals over the common denominator 26, then round the fractional-paise
    // sum half-up to whole paise (num/26) in ONE step, matching the Python single round of the sum.
    let num = old_base * 15 * pre + new_base * 15 * post;
    let paise = (num + 13) / 26;
    Paise(round_rupee(paise))
}

/// Accrued gratuity = (15/26) × last-drawn Basic × completed years.
pub fn gratuity_required(last_basic_monthly: i64, completed_years: i64) -> Paise {
    if completed_years <= 0 {
        return Paise(0);
    }
    let paise = (last_basic_monthly * 15 * completed_years + 13) / 26;
    Paise(round_rupee(paise))
}

/// Monthly statutory minimum bonus (8.33%); nil above the ₹21,000 eligibility ceiling, on Basic
/// capped at ₹7,000.
pub fn bonus_provision_monthly(basic_monthly: i64) -> Paise {
    if basic_monthly > 2_100_000 {
        return Paise(0);
    }
    let cap = basic_monthly.min(700_000);
    Paise(((cap * 833 + 500_000) / 1_000_000) * 100)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gratuity_formula() {
        // (15/26) × ₹26,000 × 5 = ₹75,000; 0 years -> nil (mirrors test_gratuity_formula).
        assert_eq!(gratuity_required(2_600_000, 5), Paise(7_500_000));
        assert_eq!(gratuity_required(2_600_000, 0), Paise(0));
    }

    #[test]
    fn bonus_provision() {
        // ₹6,000 -> 8.33% = ₹499.80 -> ₹500; ₹10,000 capped @₹7,000 = ₹583.10 -> ₹583;
        // ₹25,000 above eligibility -> nil (mirrors test_bonus_provision).
        assert_eq!(bonus_provision_monthly(600_000), Paise(50_000));
        assert_eq!(bonus_provision_monthly(1_000_000), Paise(58_300));
        assert_eq!(bonus_provision_monthly(2_500_000), Paise(0));
    }

    #[test]
    fn hybrid_vectors() {
        // Oracle vector: split old/new base -> ₹1,50,000.
        assert_eq!(
            gratuity_hybrid((2020, 11, 21), (2027, 11, 21), (2025, 11, 21), 2_600_000, 5_200_000),
            Paise(15_000_000)
        );
        // All post-boundary -> new base only -> ₹30,000.
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2028, 1, 1), (2025, 11, 21), 9_900_000, 2_600_000),
            Paise(3_000_000)
        );
        // Under one completed year -> ineligible -> nil.
        assert_eq!(
            gratuity_hybrid((2025, 6, 1), (2025, 11, 1), (2025, 11, 21), 2_600_000, 5_200_000),
            Paise(0)
        );
    }
}
