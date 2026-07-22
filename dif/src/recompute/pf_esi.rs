//! PF/ESI + Code on Wages s.2(y) wage base (mirror of app/domains/payroll/statutory.py and
//! app/core/statutory_wage.py). §WS3.1. All amounts integer paise, pure, clock-free.
//!
//! Every figure is recomputed by exact integer arithmetic: the rational product is multiplied
//! out in full and rounded (half-up) or ceiled ONCE, never truncated to whole paise first
//! (the §WS1.C3 truncate-then-round defect). The named constants match the Python module:
//! PF_WAGE_CEILING ₹15,000, ESI ceiling ₹21,000, ESI 0.75%/3.25%, PF 12%, EPS 8.33%.
use crate::money::Paise;

/// PF wage ceiling: ₹15,000 in paise.
const PF_WAGE_CEILING: i64 = 1_500_000;
/// ESI gross ceiling: ₹21,000 in paise. Gross above this => ESI not applicable.
const ESI_WAGE_CEILING: i64 = 2_100_000;

/// s.2(y) statutory wage base. `included` = the inclusion limb PLUS any component outside the
/// closed (a)-(k) exclusion list (special_allowance, unknown keys — defects #6/#7);
/// `excluded_addback` = clause (a)-(i) exclusions, the exact span the FIRST PROVISO aggregates;
/// `excluded_terminal` = clauses (j)-(k) (gratuity, retrenchment/ex-gratia) — excluded from
/// wages but OUTSIDE the add-back span (defect #5); `in_kind` = value of remuneration in kind.
/// Mirror of Python `statutory_wage_base`: add back the (a)-(i) excess over 50% of all
/// remuneration; count in-kind up to 15% of the money wage base; round half-up to whole paise.
///
/// Exact arithmetic: `base_u` carries the base as (paise × 200), so the ½-paise remainder from
/// the 50% cap and the 15% in-kind fraction stay exact until the single half-up round at the end.
pub fn statutory_wage_base(
    included: i64,
    excluded_addback: i64,
    excluded_terminal: i64,
    in_kind: i64,
) -> Paise {
    let total = included + excluded_addback + excluded_terminal;
    let mut base_u = included * 200;
    // First proviso: add back the clause (a)-(i) excess over 50% of all remuneration.
    if excluded_addback * 2 > total {
        base_u += excluded_addback * 200 - total * 100;
    }
    // Remuneration in kind counts up to 15% of the wage base (interpretation BLOCKED-CA §0.7).
    let fifteen = base_u * 3 / 20;
    let countable = (in_kind * 200).min(fifteen);
    base_u += countable;
    Paise((base_u + 100) / 200) // half-up to whole paise
}

/// (employee, employer) ESI; nil above the ₹21,000 gross ceiling. Each share is ceil(gross × rate)
/// to the next whole rupee. The exact product `gross*rate_bps/10_000` paise is fractional, so it is
/// ceiled UP to whole paise first (`+9_999`, NOT truncated — that would be the §WS1.C3 defect),
/// then `ceil_rupee` ceils to the rupee. Ceil∘ceil over finer-then-coarser grids == the exact
/// rupee-ceil, so this matches Python `_ceil_rupee(Decimal(gross)*rate)` to the paisa.
pub fn esi(gross_monthly: i64) -> (Paise, Paise) {
    if gross_monthly > ESI_WAGE_CEILING {
        return (Paise(0), Paise(0));
    }
    let emp_paise = (gross_monthly * 75 + 9_999) / 10_000; // ceil(0.75% of gross) to whole paise
    let empr_paise = (gross_monthly * 325 + 9_999) / 10_000; // ceil(3.25% of gross) to whole paise
    (
        Paise(crate::recompute::ceil_rupee(emp_paise)),
        Paise(crate::recompute::ceil_rupee(empr_paise)),
    )
}

/// PF wage = Basic (proxy for Basic+DA) capped at the ₹15,000 statutory ceiling.
fn pf_wage(basic_monthly: i64) -> i64 {
    basic_monthly.min(PF_WAGE_CEILING)
}

/// Employee PF = 12% of PF wage, rounded half-up to the whole rupee.
pub fn pf_employee(basic_monthly: i64) -> Paise {
    let w = pf_wage(basic_monthly);
    Paise(((w * 12 + 5_000) / 10_000) * 100)
}

/// Employer PF share = 12% of PF wage (same as employee share here).
pub fn pf_employer(basic_monthly: i64) -> Paise {
    pf_employee(basic_monthly)
}

/// Employer EPS share = 8.33% of PF wage (capped at ₹15,000 => max ₹1,250), half-up to rupee.
pub fn eps_employer(basic_monthly: i64) -> Paise {
    let w = pf_wage(basic_monthly);
    Paise(((w * 833 + 500_000) / 1_000_000) * 100)
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- ESI (mirrors test_statutory.py ESI cases + esi_20001_gross_ceil oracle vector) ----
    #[test]
    fn esi_below_ceiling_rounds_up() {
        // gross ₹15,000: employee 0.75%=₹112.50->ceil ₹113; employer 3.25%=₹487.50->ceil ₹488
        let (emp, empr) = esi(1_500_000);
        assert_eq!(emp, Paise(11_300));
        assert_eq!(empr, Paise(48_800));
    }

    #[test]
    fn esi_20001_gross_ceil_vector() {
        // gross ₹20,001: employee ₹150.0075->ceil ₹151; employer ₹650.0325->ceil ₹651
        let (emp, empr) = esi(2_000_100);
        assert_eq!(emp, Paise(15_100));
        assert_eq!(empr, Paise(65_100));
    }

    #[test]
    fn esi_nil_above_ceiling() {
        // gross ₹25,000 > ₹21,000 ceiling -> nil
        assert_eq!(esi(2_500_000), (Paise(0), Paise(0)));
    }

    #[test]
    fn esi_exactly_at_ceiling_applies() {
        // gross ₹21,000 == ceiling -> still applicable (strict > in the guard)
        let (emp, empr) = esi(2_100_000);
        assert_eq!(emp, Paise(15_800)); // 0.75%=₹157.50->ceil ₹158
        assert_eq!(empr, Paise(68_300)); // 3.25%=₹682.50->ceil ₹683
    }

    // ---- PF / EPS (mirrors test_statutory.py PF cases) ----
    #[test]
    fn pf_capped_at_ceiling() {
        // basic ₹50,000 -> PF wage capped at ₹15,000 -> 12% = ₹1,800
        assert_eq!(pf_employee(5_000_000), Paise(180_000));
        assert_eq!(pf_employer(5_000_000), Paise(180_000));
    }

    #[test]
    fn pf_below_ceiling_uses_actual_basic() {
        // basic ₹10,000 -> 12% = ₹1,200
        assert_eq!(pf_employee(1_000_000), Paise(120_000));
    }

    #[test]
    fn eps_capped_at_1250() {
        // basic ₹50,000 -> EPS wage capped at ₹15,000 -> 8.33% = ₹1,249.50 -> ₹1,250
        assert_eq!(eps_employer(5_000_000), Paise(125_000));
    }

    #[test]
    fn eps_below_ceiling() {
        // basic ₹10,000 -> 8.33% = ₹833.00 -> ₹833
        assert_eq!(eps_employer(1_000_000), Paise(83_300));
    }

    // ---- s.2(y) wage base (mirrors ws1b_wage_base.yaml oracle vectors) ----
    #[test]
    fn wage_base_compliant_no_addback() {
        // Basic ₹30k, HRA ₹20k; excluded ₹20k = 40% <= 50% -> base ₹30k
        assert_eq!(statutory_wage_base(3_000_000, 2_000_000, 0, 0), Paise(3_000_000));
    }

    #[test]
    fn wage_base_addback_when_basic_underweighted() {
        // Basic ₹20k, (a)-(i) excluded ₹40k > ₹30k cap -> add back ₹10k -> ₹30k
        assert_eq!(statutory_wage_base(2_000_000, 4_000_000, 0, 0), Paise(3_000_000));
    }

    #[test]
    fn wage_base_terminal_outside_addback_span() {
        // Defect #5: Basic ₹20k, HRA ₹25k, gratuity ₹15k. All remuneration ₹60k, cap ₹30k;
        // the (a)-(i) aggregate is ₹25k <= ₹30k -> NO add-back -> base ₹20k. Under the old
        // one-bucket reading gratuity drove a false ₹10k add-back (-> ₹30k).
        assert_eq!(statutory_wage_base(2_000_000, 2_500_000, 1_500_000, 0), Paise(2_000_000));
    }

    #[test]
    fn wage_base_in_kind_capped_15pct() {
        // Basic ₹30k, in-kind ₹10k; countable = min(₹10k, 15% of ₹30k = ₹4,500) -> ₹34,500
        assert_eq!(statutory_wage_base(3_000_000, 0, 0, 1_000_000), Paise(3_450_000));
    }
}
