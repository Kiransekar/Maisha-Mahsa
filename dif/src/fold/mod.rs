//! Fold: snapshot → intent. The global fold always runs; a domain fold runs when a
//! recognised domain is supplied, then blends in 20% global influence (PRD §4.3).

pub mod compliance;
pub mod equity;
pub mod global;
pub mod gst;
pub mod payables;
pub mod payroll;
pub mod revenue;
pub mod tax;
pub mod treasury;

use crate::intent::IntentVec;
use crate::snapshot::{Domain, Snapshot};

/// Which expected health signals were present vs absent in the snapshot for this fold.
/// A fold over a sparse snapshot now scores low (absent signal = worst, §0.4); this reports
/// *why* so honest-state (WS3.5) can render the honest-pending mark. We produce it here; we
/// do not render it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Completeness {
    /// Signal keys this fold expects in the snapshot `metrics` bag.
    pub expected: Vec<String>,
    /// The subset of `expected` that was absent (folded to worst).
    pub missing: Vec<String>,
    /// True iff every expected signal was present.
    pub complete: bool,
}

/// Result of folding a snapshot.
#[derive(Debug, Clone)]
pub struct Fold {
    pub global: IntentVec,
    /// Present only when a recognised domain was supplied *and* a domain fold exists.
    pub domain: Option<(Domain, IntentVec)>,
    /// Which expected signals were present vs absent (for the supplied domain, or the global
    /// fold when no domain was supplied).
    pub completeness: Completeness,
}

/// Run the global fold, and the domain sub-fold if `domain` is recognised and implemented.
pub fn fold(snapshot: &Snapshot, domain: Option<Domain>) -> Fold {
    let global = global::fold_global(snapshot);
    let completeness = completeness(snapshot, domain);
    let domain = domain.and_then(|d| domain_fold(d, snapshot, global).map(|iv| (d, iv)));
    Fold {
        global,
        domain,
        completeness,
    }
}

/// Health signals a fold expects, keyed by the supplied domain. Domains without a dedicated
/// fold (or no domain at all) fall back to the global fold's expected signals.
fn expected_signals(domain: Option<Domain>) -> &'static [&'static str] {
    match domain {
        Some(Domain::Treasury) => treasury::EXPECTED_SIGNALS,
        Some(Domain::Payroll) => payroll::EXPECTED_SIGNALS,
        Some(Domain::Gst) => gst::EXPECTED_SIGNALS,
        Some(Domain::Revenue) => revenue::EXPECTED_SIGNALS,
        Some(Domain::Payables) => payables::EXPECTED_SIGNALS,
        Some(Domain::Tax) => tax::EXPECTED_SIGNALS,
        Some(Domain::Compliance) => compliance::EXPECTED_SIGNALS,
        Some(Domain::Equity) => equity::EXPECTED_SIGNALS,
        _ => global::EXPECTED_SIGNALS,
    }
}

/// Compute snapshot completeness for the fold: which expected signals are present vs absent.
fn completeness(snapshot: &Snapshot, domain: Option<Domain>) -> Completeness {
    let expected = expected_signals(domain);
    let missing: Vec<String> = expected
        .iter()
        .filter(|k| snapshot.metric(k).is_none())
        .map(|k| k.to_string())
        .collect();
    Completeness {
        expected: expected.iter().map(|k| k.to_string()).collect(),
        complete: missing.is_empty(),
        missing,
    }
}

/// Dispatch to a domain sub-fold. Returns `None` for domains not yet implemented
/// (so the caller cleanly degrades to the global-only result).
fn domain_fold(domain: Domain, snapshot: &Snapshot, global: IntentVec) -> Option<IntentVec> {
    match domain {
        Domain::Treasury => Some(treasury::fold_treasury(snapshot).blend(global, 0.20)),
        Domain::Payroll => Some(payroll::fold_payroll(snapshot).blend(global, 0.20)),
        Domain::Gst => Some(gst::fold_gst(snapshot).blend(global, 0.20)),
        Domain::Revenue => Some(revenue::fold_revenue(snapshot).blend(global, 0.20)),
        Domain::Payables => Some(payables::fold_payables(snapshot).blend(global, 0.20)),
        Domain::Tax => Some(tax::fold_tax(snapshot).blend(global, 0.20)),
        Domain::Compliance => Some(compliance::fold_compliance(snapshot).blend(global, 0.20)),
        Domain::Equity => Some(equity::fold_equity(snapshot).blend(global, 0.20)),
        // Other domain folds are added here as each module is built (see BUILD_PROGRESS.md).
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sparse_domain_snapshot_is_degraded_and_incomplete() {
        // A payroll fold with none of its expected signals present must score low AND report
        // every expected signal as missing (§0.4: absent signal = unknown, never healthy).
        let s = Snapshot::default();
        let f = fold(&s, Some(Domain::Payroll));
        let (_, dv) = f.domain.expect("payroll fold present");
        assert!(dv.score() < 25.0, "sparse payroll scored {}", dv.score());
        assert!(!f.completeness.complete);
        assert_eq!(f.completeness.missing, f.completeness.expected);
        assert_eq!(f.completeness.expected.len(), 8);
    }

    #[test]
    fn partial_snapshot_reports_only_the_missing_signal() {
        let mut s = Snapshot::default();
        // Supply all but one payroll signal.
        for k in payroll::EXPECTED_SIGNALS.iter().filter(|k| **k != "lwf_state") {
            s.metrics.insert((*k).into(), 1.0);
        }
        let f = fold(&s, Some(Domain::Payroll));
        assert!(!f.completeness.complete);
        assert_eq!(f.completeness.missing, vec!["lwf_state".to_string()]);
    }

    #[test]
    fn complete_snapshot_reports_complete() {
        let mut s = Snapshot::default();
        for k in gst::EXPECTED_SIGNALS {
            s.metrics.insert((*k).into(), 1.0);
        }
        let f = fold(&s, Some(Domain::Gst));
        assert!(f.completeness.complete);
        assert!(f.completeness.missing.is_empty());
        // and with every signal healthy, the domain fold is healthy (the 20% global blend
        // keeps it below a perfect 100).
        assert!(f.domain.unwrap().1.score() > 90.0);
    }

    #[test]
    fn no_domain_falls_back_to_global_expected() {
        let f = fold(&Snapshot::default(), None);
        assert_eq!(f.completeness.expected, vec!["tax_efficiency".to_string()]);
        assert!(!f.completeness.complete);
    }
}
