//! TDS-on-payments section engine 194C/194J/194H/194I (mirror of
//! app/domains/payables/payables_calc.py::tds_on_payment / tds_rate / _TDS_SECTIONS, FY 2025-26
//! thresholds incl. the §WS1.C1/C2 fixes: 194J single=aggregate ₹50k; 194I ₹50k per-month with
//! NO annual aggregate). §WS3.1. All amounts integer paise, pure, clock-free.
use crate::money::Paise;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Tds {
    pub applicable: bool,
    pub tds_paise: Paise,
}

/// Section config: (single per-transaction threshold, aggregate annual threshold, per_month).
/// Mirror of `_TDS_SECTIONS`. `per_month` sections (194I) use the single threshold only — the
/// annual aggregate does not apply (§WS1.C2). Thresholds in paise (₹ × 100).
fn section_cfg(section: &str) -> Option<(i64, i64, bool)> {
    match section {
        "194C" => Some((3_000_000, 10_000_000, false)), // single ₹30k, aggregate ₹1L
        "194J" => Some((5_000_000, 5_000_000, false)),  // single = aggregate ₹50k (§WS1.C1)
        "194H" => Some((2_000_000, 2_000_000, false)),  // ₹20k
        "194I" => Some((5_000_000, 0, true)),           // ₹50k PER MONTH, no aggregate (§WS1.C2)
        _ => None,
    }
}

/// TDS rate (whole percent) for a section. Mirror of `tds_rate`. `payee_type` selects the 194C
/// contractor rate (1% individual/HUF else 2%); `category` selects 194J technical (2%) and 194I
/// plant (2%) sub-rates.
fn tds_rate(section: &str, payee_type: &str, category: Option<&str>) -> i64 {
    match section {
        "194C" => {
            if payee_type == "individual" || payee_type == "huf" {
                1
            } else {
                2
            }
        }
        "194J" => {
            if category == Some("technical") {
                2
            } else {
                10
            }
        }
        // 194I: plant & machinery 2%, else (land/building/furniture) 10%.
        "194I" => {
            if category == Some("plant") {
                2
            } else {
                10
            }
        }
        _ => 2, // 194H (and any other rate-flat section)
    }
}

/// TDS on a single payment of `amount` paise (taxable value). `category` selects the sub-rate
/// (e.g. "technical" for 194J, "plant" for 194I); `aggregate_ytd` is the running annual total.
/// `payee_type` is fixed to "company" here (the parity vectors do not exercise the 194C
/// individual/HUF variant; `tds_rate` covers it and is unit-tested directly).
pub fn tds_on_payment(
    section: &str,
    amount: i64,
    category: Option<&str>,
    aggregate_ytd: i64,
) -> Tds {
    let Some((single, aggregate, per_month)) = section_cfg(section) else {
        return Tds { applicable: false, tds_paise: Paise(0) };
    };
    let applies = if per_month {
        amount >= single
    } else {
        amount >= single || aggregate_ytd + amount >= aggregate
    };
    if !applies {
        return Tds { applicable: false, tds_paise: Paise(0) };
    }
    let rate = tds_rate(section, "company", category);
    // Python does ONE rounding: _round_rupee(Decimal(amount) * rate / 100) rounds the exact paise
    // product straight to the rupee. amount*rate/100 paise ÷100 = amount*rate/10000 rupees, half-up
    // = (amount*rate + 5000)/10000, ×100 for paise. A two-stage round (paise then rupee) diverges
    // on fractional-paise amounts, e.g. 194I @10% on ₹50,004.95 → ₹5,000 not ₹5,001.
    let tds = ((amount * rate + 5000) / 10000) * 100;
    Tds { applicable: true, tds_paise: Paise(tds) }
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- oracle vectors (ws1c_proven_defects.yaml) ---
    #[test]
    fn tds_194j_50k_boundary() {
        // ₹50,000 at threshold -> 10% = ₹5,000.
        let r = tds_on_payment("194J", 5_000_000, None, 0);
        assert!(r.applicable);
        assert_eq!(r.tds_paise, Paise(500_000));
    }

    #[test]
    fn tds_194j_below_new_threshold() {
        // ₹40,000 < ₹50,000 -> no TDS (was TDS under old ₹30k).
        let r = tds_on_payment("194J", 4_000_000, None, 0);
        assert!(!r.applicable);
        assert_eq!(r.tds_paise, Paise(0));
    }

    #[test]
    fn tds_194i_40k_no_tds() {
        // ₹40,000/mo below per-month threshold; big YTD must NOT drag it into TDS.
        let r = tds_on_payment("194I", 4_000_000, Some("building"), 12_000_000);
        assert!(!r.applicable);
        assert_eq!(r.tds_paise, Paise(0));
    }

    #[test]
    fn tds_194i_55k_full_month() {
        // ₹55,000/mo crosses -> full month at 10% = ₹5,500.
        let r = tds_on_payment("194I", 5_500_000, Some("building"), 0);
        assert!(r.applicable);
        assert_eq!(r.tds_paise, Paise(550_000));
    }

    // --- mirror of test_payables_calc.py ---
    #[test]
    fn t_194j_professional_above_threshold() {
        let r = tds_on_payment("194J", 5_000_000, None, 0);
        assert!(r.applicable);
        assert_eq!(r.tds_paise, Paise(500_000)); // 10%
    }

    #[test]
    fn t_194j_below_threshold_no_tds() {
        let r = tds_on_payment("194J", 2_000_000, None, 0);
        assert!(!r.applicable);
        assert_eq!(r.tds_paise, Paise(0));
    }

    #[test]
    fn t_194c_rate_depends_on_payee_type() {
        // Rust public fn defaults payee_type="company" (2%); the individual/HUF 1% variant is
        // covered via tds_rate directly since the signature carries no payee_type.
        let company = tds_on_payment("194C", 4_000_000, None, 0);
        assert_eq!(company.tds_paise, Paise(80_000)); // 2% of ₹40k = ₹800
        assert_eq!(tds_rate("194C", "individual", None), 1);
        assert_eq!(tds_rate("194C", "huf", None), 1);
        assert_eq!(tds_rate("194C", "company", None), 2);
    }

    #[test]
    fn t_194c_aggregate_threshold_triggers_tds() {
        // single ₹20k < ₹30k, but YTD ₹90k + ₹20k = ₹1.1L >= ₹1L aggregate -> TDS applies.
        let r = tds_on_payment("194C", 2_000_000, None, 9_000_000);
        assert!(r.applicable);
        assert_eq!(r.tds_paise, Paise(40_000)); // 2% of ₹20k = ₹400
    }

    #[test]
    fn t_194h_and_194i_rates() {
        // 194H ₹25k -> 2% = ₹500.
        assert_eq!(tds_on_payment("194H", 2_500_000, None, 0).tds_paise, Paise(50_000));
        let plant = tds_on_payment("194I", 30_000_000, Some("plant"), 0);
        let building = tds_on_payment("194I", 30_000_000, Some("building"), 0);
        assert_eq!(plant.tds_paise, Paise(600_000)); // 2% of ₹3L = ₹6,000
        assert_eq!(building.tds_paise, Paise(3_000_000)); // 10% of ₹3L = ₹30,000
    }

    #[test]
    fn t_fractional_paise_single_round_matches_python() {
        // Regression (§WS3.1 verifier): 194I building @10% on ₹50,004.95 (5_000_495 paise, above
        // the ₹50k/month threshold). Exact product = ₹5,000.495 → single round-to-rupee = ₹5,000.
        // A two-stage (paise-then-rupee) round would wrongly give ₹5,001.
        let r = tds_on_payment("194I", 5_000_495, Some("building"), 0);
        assert!(r.applicable);
        assert_eq!(r.tds_paise, Paise(500_000));
    }

    #[test]
    fn t_194j_technical_rate() {
        // technical/call-centre 194J -> 2% of ₹1L = ₹2,000.
        let r = tds_on_payment("194J", 10_000_000, Some("technical"), 0);
        assert_eq!(r.tds_paise, Paise(200_000));
    }

    #[test]
    fn t_unknown_section_not_applicable() {
        let r = tds_on_payment("999X", 10_000_000, None, 0);
        assert!(!r.applicable);
        assert_eq!(r.tds_paise, Paise(0));
    }
}
