//! Revenue sub-vector fold (PRD §1.2 / §2.2). Dimensions (in order):
//! ar_turnover, dunning_effectiveness, credit_risk, revenue_quality, deferred_revenue,
//! export_ratio, irn_coverage, customer_concentration.
//!
//! The Python service computes each health signal (AR aging, IRN coverage, concentration)
//! and passes it via the snapshot `metrics` bag. Missing signals default to healthy.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(1.0).clamp(0.0, 1.0)
}

pub fn fold_revenue(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "ar_turnover"),
        health(s, "dunning_effectiveness"),
        health(s, "credit_risk"),
        health(s, "revenue_quality"),
        health(s, "deferred_revenue"),
        health(s, "export_ratio"),
        health(s, "irn_coverage"),
        health(s, "customer_concentration"),
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_healthy_and_is_deterministic() {
        let s = Snapshot::default();
        let v = fold_revenue(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 100.0);
        assert_eq!(v, fold_revenue(&s));
    }

    #[test]
    fn surfaces_credit_and_concentration_risk() {
        let mut s = Snapshot::default();
        s.metrics.insert("credit_risk".into(), 0.3);
        s.metrics.insert("customer_concentration".into(), 0.2);
        let v = fold_revenue(&s);
        assert_eq!(v.0[2], 0.3);
        assert_eq!(v.0[7], 0.2);
    }
}
