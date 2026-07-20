//! GSTR-3B late fee + interest (mirror of app/domains/gst/gst_calc.py::late_fee_3b /
//! interest_3b). §WS3.1. All amounts integer paise; `days_late` injected, no clock.

const LATE_FEE_PER_DAY: i64 = 5000; // ₹50/day (CGST ₹25 + SGST ₹25), paise
const LATE_FEE_PER_DAY_NIL: i64 = 2000; // ₹20/day for nil returns
const LATE_FEE_CAP: i64 = 1_000_000; // ₹10,000 cap
const LATE_FEE_CAP_NIL: i64 = 50_000; // ₹500 cap for nil returns

pub fn late_fee_3b(days_late: i64, is_nil: bool) -> i64 {
    if days_late <= 0 {
        return 0;
    }
    let per_day = if is_nil { LATE_FEE_PER_DAY_NIL } else { LATE_FEE_PER_DAY };
    let cap = if is_nil { LATE_FEE_CAP_NIL } else { LATE_FEE_CAP };
    (per_day * days_late).min(cap)
}

pub fn interest_3b(cash_tax: i64, days_late: i64) -> i64 {
    if days_late <= 0 || cash_tax <= 0 {
        return 0;
    }
    // interest (exact, paise) = cash_tax * 0.18 * days_late / 365 = num / 36500.
    // Python first rounds this to the nearest integer paisa (ROUND_HALF_UP), then rounds
    // that to the nearest rupee via _round_rupee. Mirror both steps, never truncating the
    // fractional-paise product before rounding (§WS1.C3).
    let num = cash_tax * 18 * days_late;
    let paise = (num + 18_250) / 36_500; // round_half_up(num / 36500); 36500/2 = 18250
    crate::recompute::round_rupee(paise)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Mirrors api/tests/unit/gst/test_gst_calc.py::test_late_fee_normal_nil_and_cap
    #[test]
    fn late_fee_normal_nil_and_cap() {
        assert_eq!(late_fee_3b(5, false), 25_000); // ₹50/day × 5 = ₹250
        assert_eq!(late_fee_3b(5, true), 10_000); // ₹20/day × 5 = ₹100
        assert_eq!(late_fee_3b(1000, false), LATE_FEE_CAP); // capped at ₹10,000
        assert_eq!(late_fee_3b(0, false), 0);
    }

    // Mirrors api/tests/unit/gst/test_gst_calc.py::test_interest_18pct_simple
    #[test]
    fn interest_18pct_simple() {
        // ₹10,000 × 18% × 30/365 = ₹147.95 -> ₹148
        assert_eq!(interest_3b(1_000_000, 30), 14_800);
        assert_eq!(interest_3b(1_000_000, 0), 0);
    }

    #[test]
    fn late_fee_nil_cap() {
        assert_eq!(late_fee_3b(30, true), LATE_FEE_CAP_NIL); // ₹20 × 30 = ₹600 -> capped ₹500
    }

    #[test]
    fn interest_zero_cash_tax() {
        assert_eq!(interest_3b(0, 30), 0);
        assert_eq!(interest_3b(-100, 30), 0);
    }
}
