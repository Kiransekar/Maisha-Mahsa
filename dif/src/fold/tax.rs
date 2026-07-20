//! Tax sub-vector fold (PRD §1.6 / §2.2). Dimensions (in order):
//! advance_tax_coverage, tds_deposit_timeliness, as26_match, audit_trigger, mat_exposure,
//! holiday_utilization, tp_documentation, itr_accuracy.
//!
//! The Python service computes each health signal (advance-tax coverage, TDS deposit
//! timeliness, 26AS match) and passes it via the snapshot `metrics` bag. A missing signal
//! folds to `0.0` (worst): an absent domain signal is "unknown", never healthy (§0.4).

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

/// The health signals this fold expects in the snapshot `metrics` bag (drives completeness).
pub const EXPECTED_SIGNALS: &[&str] = &[
    "advance_tax_coverage",
    "tds_deposit_timeliness",
    "as26_match",
    "audit_trigger",
    "mat_exposure",
    "holiday_utilization",
    "tp_documentation",
    "itr_accuracy",
];

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(0.0).clamp(0.0, 1.0)
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
    fn absent_signals_fold_degraded_not_healthy() {
        // §0.4: an absent domain signal is unknown, never healthy.
        let s = Snapshot::default();
        let v = fold_tax(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 0.0);
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
