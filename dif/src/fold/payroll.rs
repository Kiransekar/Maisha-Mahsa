//! Payroll sub-vector fold (PRD §1.4 / §2.2). Dimensions (in order):
//! pf_compliance, esi_compliance, tds_accuracy, pt_state, lwf_state, gratuity_reserve,
//! bonus_reserve, leave_liability.
//!
//! The heavy statutory math lives in the (exhaustively unit-tested) Python service, which
//! reduces each dimension to a health score in `[0,1]` and passes it via the snapshot
//! `metrics` bag. This fold reads those health signals and blends global influence. A
//! missing signal defaults to `1.0` (healthy) so a sparse snapshot still folds — the
//! Python side is responsible for surfacing real shortfalls.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(1.0).clamp(0.0, 1.0)
}

pub fn fold_payroll(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "pf_compliance"),
        health(s, "esi_compliance"),
        health(s, "tds_accuracy"),
        health(s, "pt_state"),
        health(s, "lwf_state"),
        health(s, "gratuity_reserve"),
        health(s, "bonus_reserve"),
        health(s, "leave_liability"),
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_healthy_when_signals_absent() {
        let s = Snapshot::default();
        let v = fold_payroll(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 100.0);
    }

    #[test]
    fn surfaces_supplied_shortfalls_and_is_deterministic() {
        let mut s = Snapshot::default();
        s.metrics.insert("pf_compliance".into(), 0.0);
        s.metrics.insert("tds_accuracy".into(), 0.5);
        let v = fold_payroll(&s);
        assert!(v.is_normalized());
        assert_eq!(v.0[0], 0.0); // pf_compliance
        assert_eq!(v.0[2], 0.5); // tds_accuracy
        assert_eq!(v, fold_payroll(&s));
    }
}
