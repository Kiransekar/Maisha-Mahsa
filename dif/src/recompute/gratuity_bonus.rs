//! Gratuity (incl. the §WS1.B2 hybrid transition) + statutory minimum bonus (mirror of
//! app/domains/payroll/statutory.py). §WS3.1. All amounts integer paise; dates injected.
use crate::money::Paise;
use crate::recompute::round_rupee;

/// A calendar date as (year, month, day) — dates are injected, no clock, no chrono dependency.
pub type Ymd = (i32, u32, u32);

/// CoSS 2020 s.53(3) notified ceiling: ₹20,00,000 (S.O. 1420(E) 29-03-2018 under PoG Act 1972
/// s.4(3), carried into s.53(3) by CoSS s.164(2)(a)). Mirror of Python `GRATUITY_CEILING`.
const GRATUITY_CEILING: i64 = 200_000_000;
/// CoSS 2020 s.53(1): continuous service "for not less than five years".
const GRATUITY_MIN_YEARS: i64 = 5;
/// FTE floor: s.53(1) second proviso disapplies five years for fixed-term expiry; MoLE FAQ
/// (16.03.2026) Sl.14/19 fixes one year.
const GRATUITY_MIN_YEARS_FIXED_TERM: i64 = 1;

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
/// both legs use 15/26; result capped at the s.53(3) ceiling. Eligibility (defect #3, fixed):
/// five completed years per s.53(1), one year only when `fixed_term` (the statute's own
/// exception). Mirror the Python rounding EXACTLY: round the fractional-paise sum half-up to
/// whole paise, THEN half-up to whole rupee, THEN cap.
pub fn gratuity_hybrid(
    doj: Ymd,
    exit_date: Ymd,
    boundary: Ymd,
    old_base: i64,
    new_base: i64,
    fixed_term: bool,
) -> Paise {
    let total = completed_years(doj, exit_date);
    let floor = if fixed_term { GRATUITY_MIN_YEARS_FIXED_TERM } else { GRATUITY_MIN_YEARS };
    if total < floor {
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
    Paise(round_rupee(paise).min(GRATUITY_CEILING))
}

/// Accrued gratuity = (15/26) × last-drawn Basic × completed years, capped at the s.53(3)
/// ceiling (defect #4, fixed).
pub fn gratuity_required(last_basic_monthly: i64, completed_years: i64) -> Paise {
    if completed_years <= 0 {
        return Paise(0);
    }
    let paise = (last_basic_monthly * 15 * completed_years + 13) / 26;
    Paise(round_rupee(paise).min(GRATUITY_CEILING))
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
    fn gratuity_required_ceiling_pair() {
        // s.53(3) ceiling ₹20,00,000. PAIRED: below the cap passes through untouched;
        // above it clamps to exactly the cap.
        // ₹2,00,000 × 17y: (15/26)×20,000,000×17 = 196,153,846.15 -> ₹19,61,538 < cap.
        assert_eq!(gratuity_required(20_000_000, 17), Paise(196_153_800));
        // ₹2,00,000 × 18y: raw ₹20,76,923 > cap -> exactly ₹20,00,000.
        assert_eq!(gratuity_required(20_000_000, 18), Paise(200_000_000));
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
        // Oracle vector: 7 completed years (>= 5, eligible), split old/new base -> ₹1,50,000.
        assert_eq!(
            gratuity_hybrid(
                (2020, 11, 21), (2027, 11, 21), (2025, 11, 21), 2_600_000, 5_200_000, false
            ),
            Paise(15_000_000)
        );
        // Under one completed year -> ineligible on every reading -> nil.
        assert_eq!(
            gratuity_hybrid(
                (2025, 6, 1), (2025, 11, 1), (2025, 11, 21), 2_600_000, 5_200_000, false
            ),
            Paise(0)
        );
    }

    #[test]
    fn hybrid_five_year_floor_pair() {
        // CoSS 2020 s.53(1): "continuous service for not less than five years". PAIRED:
        // exactly 5 completed years -> payable (15/26 × ₹26,000 × 5 = ₹75,000)…
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2031, 1, 1), (2025, 11, 21), 9_900_000, 2_600_000, false),
            Paise(7_500_000)
        );
        // …one day short of the 5th anniversary (4 completed years) -> nil for a non-FTE.
        assert_eq!(
            gratuity_hybrid(
                (2026, 1, 1), (2030, 12, 31), (2025, 11, 21), 9_900_000, 2_600_000, false
            ),
            Paise(0)
        );
    }

    #[test]
    fn hybrid_fte_one_year_floor_pair() {
        // FTE exception (s.53(1) second proviso + MoLE FAQ Sl.14): PAIRED at the 1-year floor.
        // Exactly 1 completed year, fixed_term -> (15/26) × ₹26,000 × 1 = ₹15,000…
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2027, 1, 1), (2025, 11, 21), 9_900_000, 2_600_000, true),
            Paise(1_500_000)
        );
        // …11 months (0 completed years), fixed_term -> nil (FAQ Sl.19).
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2026, 12, 1), (2025, 11, 21), 9_900_000, 2_600_000, true),
            Paise(0)
        );
        // The FTE floor is the EXCEPTION, not the rule: same 2 years non-FTE -> nil, FTE -> ₹30,000.
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2028, 1, 1), (2025, 11, 21), 9_900_000, 2_600_000, false),
            Paise(0)
        );
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2028, 1, 1), (2025, 11, 21), 9_900_000, 2_600_000, true),
            Paise(3_000_000)
        );
    }

    #[test]
    fn hybrid_ceiling_pair() {
        // s.53(3) ceiling ₹20,00,000, PAIRED. 17y × ₹2,00,000 base = ₹19,61,538 -> under cap…
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2043, 1, 1), (2025, 11, 21), 0, 20_000_000, false),
            Paise(196_153_800)
        );
        // …18y raw ₹20,76,923 -> clamps to exactly the cap.
        assert_eq!(
            gratuity_hybrid((2026, 1, 1), (2044, 1, 1), (2025, 11, 21), 0, 20_000_000, false),
            Paise(200_000_000)
        );
    }
}
