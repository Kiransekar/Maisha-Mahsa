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

/// Result of folding a snapshot.
#[derive(Debug, Clone)]
pub struct Fold {
    pub global: IntentVec,
    /// Present only when a recognised domain was supplied *and* a domain fold exists.
    pub domain: Option<(Domain, IntentVec)>,
}

/// Run the global fold, and the domain sub-fold if `domain` is recognised and implemented.
pub fn fold(snapshot: &Snapshot, domain: Option<Domain>) -> Fold {
    let global = global::fold_global(snapshot);
    let domain = domain.and_then(|d| domain_fold(d, snapshot, global).map(|iv| (d, iv)));
    Fold { global, domain }
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
