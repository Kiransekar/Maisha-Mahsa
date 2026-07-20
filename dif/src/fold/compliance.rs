//! Compliance sub-vector fold (PRD §1.10 / §2.2). Dimensions (in order):
//! roc_filing_status, gst_filing_status, tds_filing_status, pf_filing_status,
//! esi_filing_status, pt_filing_status, secretarial_score, audit_readiness.
//!
//! The Python service derives each filing-status signal from the compliance calendar (1.0
//! when nothing is overdue for that statute, else 0.0) and passes it via the snapshot
//! `metrics` bag. A missing signal folds to `0.0` (worst): an absent domain signal is
//! "unknown", never healthy (§0.4) — a compliance fold with no calendar data must not claim
//! clean.

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

/// The health signals this fold expects in the snapshot `metrics` bag (drives completeness).
pub const EXPECTED_SIGNALS: &[&str] = &[
    "roc_filing_status",
    "gst_filing_status",
    "tds_filing_status",
    "pf_filing_status",
    "esi_filing_status",
    "pt_filing_status",
    "secretarial_score",
    "audit_readiness",
];

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(0.0).clamp(0.0, 1.0)
}

pub fn fold_compliance(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "roc_filing_status"),
        health(s, "gst_filing_status"),
        health(s, "tds_filing_status"),
        health(s, "pf_filing_status"),
        health(s, "esi_filing_status"),
        health(s, "pt_filing_status"),
        health(s, "secretarial_score"),
        health(s, "audit_readiness"),
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
        let v = fold_compliance(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 0.0);
        assert_eq!(v, fold_compliance(&s));
    }

    #[test]
    fn surfaces_overdue_filing_status() {
        let mut s = Snapshot::default();
        s.metrics.insert("gst_filing_status".into(), 0.0);
        s.metrics.insert("tds_filing_status".into(), 0.0);
        let v = fold_compliance(&s);
        assert_eq!(v.0[1], 0.0);
        assert_eq!(v.0[2], 0.0);
    }
}
