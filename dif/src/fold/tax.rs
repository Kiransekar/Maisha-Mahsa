//! Tax sub-vector fold (PRD §1.6 / §2.2). Dimensions (in order):
//! advance_tax_coverage, tds_deposit_timeliness, as26_match, audit_trigger, mat_exposure,
//! holiday_utilization, tp_documentation, itr_accuracy.
//!
//! The Python service computes each health signal (advance-tax coverage, TDS deposit
//! timeliness, 26AS match) and passes it via the snapshot `metrics` bag. Missing signals
//! default to healthy.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(1.0).clamp(0.0, 1.0)
}

pub fn fold_tax(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "advance_tax_coverage"),
        health(s, "tds_deposit_timeliness"),
        health(s, "as26_match"),
        health(s, "audit_trigger"),
        health(s, "mat_exposure"),
        health(s, "holiday_utilization"),
        health(s, "tp_documentation"),
        health(s, "itr_accuracy"),
    ])
    .clamped()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_healthy_and_is_deterministic() {
        let s = Snapshot::default();
        let v = fold_tax(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 100.0);
        assert_eq!(v, fold_tax(&s));
    }

    #[test]
    fn surfaces_advance_tax_and_tds_signals() {
        let mut s = Snapshot::default();
        s.metrics.insert("advance_tax_coverage".into(), 0.1);
        s.metrics.insert("tds_deposit_timeliness".into(), 0.0);
        let v = fold_tax(&s);
        assert_eq!(v.0[0], 0.1);
        assert_eq!(v.0[1], 0.0);
    }
}
