//! Equity sub-vector fold (PRD §1.9 / §2.2). Dimensions (in order):
//! dilution_rate, esop_utilization, safe_conversion_complexity, investor_reporting_timeliness,
//! dividend_capacity, share_pricing_fairness, board_compliance, cap_table_accuracy.
//!
//! The Python service derives each signal from the cap table / SAFE notes and passes it via
//! the snapshot `metrics` bag. Missing signals default to healthy.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(1.0).clamp(0.0, 1.0)
}

pub fn fold_equity(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "dilution_rate"),
        health(s, "esop_utilization"),
        health(s, "safe_conversion_complexity"),
        health(s, "investor_reporting_timeliness"),
        health(s, "dividend_capacity"),
        health(s, "share_pricing_fairness"),
        health(s, "board_compliance"),
        health(s, "cap_table_accuracy"),
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_healthy_and_is_deterministic() {
        let s = Snapshot::default();
        let v = fold_equity(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 100.0);
        assert_eq!(v, fold_equity(&s));
    }

    #[test]
    fn surfaces_captable_and_dilution_signals() {
        let mut s = Snapshot::default();
        s.metrics.insert("cap_table_accuracy".into(), 0.0);
        s.metrics.insert("dilution_rate".into(), 0.3);
        let v = fold_equity(&s);
        assert_eq!(v.0[7], 0.0);
        assert_eq!(v.0[0], 0.3);
    }
}
