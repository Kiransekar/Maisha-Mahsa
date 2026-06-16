//! Treasury sub-vector fold (PRD §1.1 / §2.2). Dimensions (in order):
//! runway_months, burn_stability, cash_concentration, fd_exposure, forex_exposure,
//! credit_line_utilization, sweep_efficiency, liquidity_stress.
//!
//! Inputs that have no typed `Snapshot` field are read from the `metrics` bag, with
//! neutral (0.5) defaults so a partial snapshot still folds deterministically.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

fn metric_or(s: &Snapshot, key: &str, default: f64) -> f64 {
    s.metric(key).unwrap_or(default).clamp(0.0, 1.0)
}

pub fn fold_treasury(s: &Snapshot) -> IntentVec {
    let runway = s.runway_months();
    let runway_health = if runway.is_infinite() {
        1.0
    } else {
        (runway / 12.0).clamp(0.0, 1.0)
    };

    // burn_stability: 1 - coefficient of variation of burn (supplied as metric, default stable).
    let burn_stability = 1.0 - metric_or(s, "burn_cv", 0.0);

    // cash_concentration health: lower concentration is better.
    let cash_concentration = (1.0 - s.largest_account_share.clamp(0.0, 1.0)).clamp(0.0, 1.0);

    let fd_exposure = metric_or(s, "fd_exposure", 0.5);

    let forex_exposure = if s.cash.is_zero() {
        1.0
    } else {
        (1.0 - (s.forex_exposure.rupees() / s.cash.rupees()).clamp(0.0, 1.0)).clamp(0.0, 1.0)
    };

    // credit_line_utilization health: lower utilization is better.
    let credit_line_utilization = 1.0 - metric_or(s, "credit_line_utilization_ratio", 0.0);

    let sweep_efficiency = metric_or(s, "sweep_efficiency", 0.5);

    // liquidity_stress health: short runway = high stress = low health.
    let liquidity_stress = runway_health;

    IntentVec([
        runway_health,
        burn_stability,
        cash_concentration,
        fd_exposure,
        forex_exposure,
        credit_line_utilization,
        sweep_efficiency,
        liquidity_stress,
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::money::Paise;

    #[test]
    fn treasury_fold_is_normalized_and_deterministic() {
        let s = Snapshot {
            cash: Paise::from_rupees(5_000_000),
            monthly_burn: Paise::from_rupees(500_000),
            largest_account_share: 0.4,
            ..Default::default()
        };
        let v = fold_treasury(&s);
        assert!(v.is_normalized());
        assert_eq!(v, fold_treasury(&s));
    }
}
