//! Payables sub-vector fold (PRD §1.3 / §2.2). Dimensions (in order):
//! ap_turnover, msme_compliance, tds_deposit_status, po_coverage,
//! early_pay_discount_capture, vendor_concentration, recurring_spend, dispute_rate.
//!
//! The Python service computes each health signal (AP aging, MSME ageing, 3-way match
//! coverage, concentration) and passes it via the snapshot `metrics` bag. A missing signal
//! folds to `0.0` (worst): an absent domain signal is "unknown", never healthy (§0.4).

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;

/// The health signals this fold expects in the snapshot `metrics` bag (drives completeness).
pub const EXPECTED_SIGNALS: &[&str] = &[
    "ap_turnover",
    "msme_compliance",
    "tds_deposit_status",
    "po_coverage",
    "early_pay_discount_capture",
    "vendor_concentration",
    "recurring_spend",
    "dispute_rate",
];

fn health(s: &Snapshot, key: &str) -> f64 {
    s.metric(key).unwrap_or(0.0).clamp(0.0, 1.0)
}

pub fn fold_payables(s: &Snapshot) -> IntentVec {
    IntentVec([
        health(s, "ap_turnover"),
        health(s, "msme_compliance"),
        health(s, "tds_deposit_status"),
        health(s, "po_coverage"),
        health(s, "early_pay_discount_capture"),
        health(s, "vendor_concentration"),
        health(s, "recurring_spend"),
        health(s, "dispute_rate"),
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
        let v = fold_payables(&s);
        assert!(v.is_normalized());
        assert_eq!(v.score(), 0.0);
        assert_eq!(v, fold_payables(&s));
    }

    #[test]
    fn surfaces_msme_and_concentration_signals() {
        let mut s = Snapshot::default();
        s.metrics.insert("msme_compliance".into(), 0.0);
        s.metrics.insert("vendor_concentration".into(), 0.25);
        let v = fold_payables(&s);
        assert_eq!(v.0[1], 0.0);
        assert_eq!(v.0[5], 0.25);
    }
}
