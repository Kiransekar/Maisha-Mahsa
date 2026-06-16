//! The global 8-dim fold. Deterministic, pure. Every dimension is a health score in
//! `[0,1]` (1 = healthy). Formulas are intentionally simple and explainable — Mahsa's
//! job is reproducible scoring, not cleverness.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

/// Smoothly map a "more is better" value onto `[0,1]` saturating at `good`.
fn ramp_up(value: f64, good: f64) -> f64 {
    if good <= 0.0 {
        return 1.0;
    }
    (value / good).clamp(0.0, 1.0)
}

/// Map a "less is better" ratio (`[0,1]` input) onto a health score.
fn invert(ratio: f64) -> f64 {
    (1.0 - ratio).clamp(0.0, 1.0)
}

pub fn fold_global(s: &Snapshot) -> IntentVec {
    // cash_flow: revenue covering burn. ratio revenue/burn, healthy at >= 1.0.
    let cash_flow = if s.monthly_burn.is_zero() {
        1.0
    } else {
        ramp_up(s.monthly_revenue.rupees() / s.monthly_burn.rupees(), 1.0)
    };

    // liquidity: runway months, healthy at >= 12 months.
    let runway = s.runway_months();
    let liquidity = if runway.is_infinite() {
        1.0
    } else {
        ramp_up(runway, 12.0)
    };

    // risk_exposure (health): low when runway is short or cash concentrated.
    let concentration_penalty = s.largest_account_share.clamp(0.0, 1.0);
    let risk_exposure = (liquidity * 0.6 + invert(concentration_penalty) * 0.4).clamp(0.0, 1.0);

    // tax_efficiency: proxy from the metric bag (set by the tax domain); neutral default.
    let tax_efficiency = s.metric("tax_efficiency").unwrap_or(0.5).clamp(0.0, 1.0);

    // compliance: overdue filings drag the score; each overdue filing costs 0.2.
    let compliance = (1.0 - s.overdue_filings as f64 * 0.2).clamp(0.0, 1.0);

    // diversification: more bank accounts + lower concentration is healthier.
    let accounts = ramp_up(s.bank_account_count as f64, 3.0);
    let diversification = (accounts * 0.5 + invert(concentration_penalty) * 0.5).clamp(0.0, 1.0);

    // currency_hedge: forex exposure relative to cash; lower is healthier.
    let fx_ratio = if s.cash.is_zero() {
        0.0
    } else {
        (s.forex_exposure.rupees() / s.cash.rupees()).clamp(0.0, 1.0)
    };
    let currency_hedge = invert(fx_ratio);

    // growth: bounded inverse of burn multiple (lower burn multiple = healthier growth).
    let bm = s.burn_multiple();
    let growth = if bm.is_infinite() {
        // no ARR reported: fall back to cash_flow as a weak proxy.
        cash_flow * 0.5
    } else {
        invert((bm / 3.0).clamp(0.0, 1.0))
    };

    IntentVec([
        cash_flow,
        risk_exposure,
        liquidity,
        tax_efficiency,
        compliance,
        diversification,
        currency_hedge,
        growth,
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::money::Paise;

    #[test]
    fn healthy_company_scores_high() {
        let s = Snapshot {
            cash: Paise::from_rupees(12_000_000),
            monthly_burn: Paise::from_rupees(800_000),
            monthly_revenue: Paise::from_rupees(900_000),
            monthly_new_arr: Paise::from_rupees(400_000),
            bank_account_count: 4,
            largest_account_share: 0.3,
            overdue_filings: 0,
            ..Default::default()
        };
        let v = fold_global(&s);
        assert!(v.is_normalized());
        assert!(v.score() > 70.0, "healthy company scored {}", v.score());
    }

    #[test]
    fn distressed_company_scores_low_on_liquidity() {
        let s = Snapshot {
            cash: Paise::from_rupees(500_000),
            monthly_burn: Paise::from_rupees(1_000_000),
            monthly_revenue: Paise::ZERO,
            overdue_filings: 3,
            largest_account_share: 1.0,
            ..Default::default()
        };
        let v = fold_global(&s);
        assert!(v.is_normalized());
        assert!(v.global("liquidity").unwrap() < 0.1);
        assert!(v.global("compliance").unwrap() < 0.5);
    }

    #[test]
    fn fold_is_deterministic() {
        let s = Snapshot {
            cash: Paise::from_rupees(1_000_000),
            monthly_burn: Paise::from_rupees(300_000),
            ..Default::default()
        };
        assert_eq!(fold_global(&s), fold_global(&s));
    }
}
