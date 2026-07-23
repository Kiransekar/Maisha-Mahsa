//! GSTR-3B late fee + interest (mirror of app/domains/gst/gst_calc.py::late_fee_3b /
//! interest_3b). §WS3.1. All amounts integer paise; `days_late` injected, no clock.

const LATE_FEE_PER_DAY: i64 = 5000; // ₹50/day (CGST ₹25 + SGST ₹25), paise
const LATE_FEE_PER_DAY_NIL: i64 = 2000; // ₹20/day for nil returns
const LATE_FEE_CAP: i64 = 1_000_000; // ₹10,000 combined s.47(1) statutory maximum
const LATE_FEE_CAP_NIL: i64 = 50_000; // ₹500 combined cap for nil returns (Notf 19/2021 Sl.1)

// Notf 19/2021-Central Tax turnover-linked caps (combined CGST + mirrored SGST):
// Sl.2 AATO "up to rupees 1.5 crores" → ₹1,000 CGST (₹2,000 combined);
// Sl.3 "more than rupees 1.5 crores and up to rupees 5 crores" → ₹2,500 CGST (₹5,000 combined).
const LATE_FEE_CAP_AATO_1_5CR: i64 = 200_000;
const LATE_FEE_CAP_AATO_5CR: i64 = 500_000;
const AATO_1_5CR: i64 = 1_500_000_000; // ₹1.5 crore, paise
const AATO_5CR: i64 = 5_000_000_000; // ₹5 crore, paise

/// `aato` = aggregate turnover in the preceding FY, paise. `None` (unknown) fails toward the
/// s.47(1) statutory-maximum cap — never a silent undercharge. Mirror of gst_calc.late_fee_3b.
pub fn late_fee_3b(days_late: i64, is_nil: bool, aato: Option<i64>) -> i64 {
    if days_late <= 0 {
        return 0;
    }
    let per_day = if is_nil {
        LATE_FEE_PER_DAY_NIL
    } else {
        LATE_FEE_PER_DAY
    };
    let cap = if is_nil {
        LATE_FEE_CAP_NIL // nil class regardless of turnover (Notf 19/2021 Sl.1)
    } else {
        match aato {
            None => LATE_FEE_CAP,
            Some(t) if t <= AATO_1_5CR => LATE_FEE_CAP_AATO_1_5CR,
            Some(t) if t <= AATO_5CR => LATE_FEE_CAP_AATO_5CR,
            Some(_) => LATE_FEE_CAP,
        }
    };
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
        assert_eq!(late_fee_3b(5, false, None), 25_000); // ₹50/day × 5 = ₹250
        assert_eq!(late_fee_3b(5, true, None), 10_000); // ₹20/day × 5 = ₹100
        assert_eq!(late_fee_3b(1000, false, None), LATE_FEE_CAP); // capped at ₹10,000
        assert_eq!(late_fee_3b(0, false, None), 0);
    }

    #[test]
    fn late_fee_aato_caps_notf_19_2021() {
        // AATO ≤ ₹1.5cr: ₹2,000 combined cap → binds from day 40 (₹50/day).
        let cr_1_5 = AATO_1_5CR;
        assert_eq!(late_fee_3b(39, false, Some(cr_1_5)), 195_000);
        assert_eq!(late_fee_3b(40, false, Some(cr_1_5)), 200_000);
        assert_eq!(late_fee_3b(41, false, Some(cr_1_5)), 200_000);
        // One paisa above ₹1.5cr → next class, ₹5,000 combined cap (binds from day 100).
        assert_eq!(late_fee_3b(99, false, Some(cr_1_5 + 1)), 495_000);
        assert_eq!(late_fee_3b(100, false, Some(cr_1_5 + 1)), 500_000);
        assert_eq!(late_fee_3b(201, false, Some(AATO_5CR)), 500_000);
        // Above ₹5cr, and unknown AATO, both fall back to the s.47(1) statutory maximum.
        assert_eq!(late_fee_3b(201, false, Some(AATO_5CR + 1)), 1_000_000);
        assert_eq!(late_fee_3b(201, false, None), 1_000_000);
        // Nil-return cap applies regardless of turnover (Sl.1 carve-out in Sl.2/Sl.3).
        assert_eq!(late_fee_3b(26, true, Some(cr_1_5)), 50_000);
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
        assert_eq!(late_fee_3b(30, true, None), LATE_FEE_CAP_NIL); // ₹20 × 30 = ₹600 -> ₹500
    }

    #[test]
    fn interest_zero_cash_tax() {
        assert_eq!(interest_3b(0, 30), 0);
        assert_eq!(interest_3b(-100, 30), 0);
    }
}
