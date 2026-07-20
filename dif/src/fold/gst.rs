//! GST sub-vector fold (PRD §1.5 / §2.2). Dimensions (in order):
//! filing_timeliness, itc_optimization, e_invoice_readiness, hsn_accuracy, rcm_compliance,
//! lut_validity, reconciliation_gap, penalty_exposure.
//!
//! As with payroll, the heavy GST math (GSTR-3B set-off, late fee, reconciliation) lives in
//! the unit-tested Python service, which reduces each dimension to a health score in
//! `[0,1]` and passes it via the snapshot `metrics` bag. A missing signal folds to `0.0`
//! (worst): an absent domain signal is "unknown", never healthy (MASTER_PLAN §0.4).

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

/// The health signals this fold expects in the snapshot `metrics` bag (drives completeness).
pub const EXPECTED_SIGNALS: &[&str] = &[
    "filing_timeliness",
    "itc_optimization",
    "e_invoice_readiness",
    "hsn_accuracy",
    "rcm_compliance",
    "lut_validity",
    "reconciliation_gap",
    "penalty_exposure",
];

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(0.0).clamp(0.0, 1.0)
}

pub fn fold_gst(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "filing_timeliness"),
        health(s, "itc_optimization"),
        health(s, "e_invoice_readiness"),
        health(s, "hsn_accuracy"),
        health(s, "rcm_compliance"),
        health(s, "lut_validity"),
        health(s, "reconciliation_gap"),
        health(s, "penalty_exposure"),
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
        let v = fold_gst(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 0.0);
        assert_eq!(v, fold_gst(&s));
    }

    #[test]
    fn surfaces_late_filing_signal() {
        let mut s = Snapshot::default();
        s.metrics.insert("filing_timeliness".into(), 0.0);
        s.metrics.insert("reconciliation_gap".into(), 0.4);
        let v = fold_gst(&s);
        assert_eq!(v.0[0], 0.0);
        assert_eq!(v.0[6], 0.4);
    }
}
