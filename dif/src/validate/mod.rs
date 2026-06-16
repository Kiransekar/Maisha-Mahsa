//! Hierarchical validation. Global rules are checked first, then any rules scoped to the
//! supplied domain. The overall status is the worst severity that fired.

pub mod rules;

pub use rules::{Rule, RuleSet, Severity};

use crate::intent::IntentVec;
use crate::snapshot::{Domain, Snapshot};
use serde::Serialize;

/// Traffic-light outcome that governs approval mode (PRD §2.2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ValidationStatus {
    Green,
    Yellow,
    Red,
}

impl ValidationStatus {
    fn from_severity(sev: Option<Severity>) -> Self {
        match sev {
            None => ValidationStatus::Green,
            Some(Severity::Info) | Some(Severity::Warning) => ValidationStatus::Yellow,
            Some(Severity::Block) => ValidationStatus::Red,
        }
    }
}

/// A rule that fired, with its full citation, for audit + display.
#[derive(Debug, Clone, Serialize)]
pub struct TriggeredRule {
    pub id: String,
    pub domain: String,
    pub severity: Severity,
    pub description: String,
    pub statute: String,
    pub section: String,
    pub action: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Validation {
    pub status: ValidationStatus,
    pub triggered: Vec<TriggeredRule>,
}

/// Validate an intent + snapshot against the rule set. When `domain` is `Some`, only the
/// global rules and that domain's rules are evaluated; otherwise global rules only.
pub fn validate(
    intent: &IntentVec,
    snapshot: &Snapshot,
    domain: Option<Domain>,
    rules: &RuleSet,
) -> Validation {
    let domain_name = domain.map(|d| d.as_str());
    let mut triggered = Vec::new();
    let mut worst: Option<Severity> = None;

    for r in &rules.rules {
        let in_scope = r.domain == "global" || domain_name.map(|d| d == r.domain).unwrap_or(false);
        if !in_scope {
            continue;
        }
        if r.triggers(intent, snapshot) {
            worst = Some(worst.map_or(r.severity, |w| w.max(r.severity)));
            triggered.push(TriggeredRule {
                id: r.id.clone(),
                domain: r.domain.clone(),
                severity: r.severity,
                description: r.description.clone(),
                statute: r.statute.clone(),
                section: r.section.clone(),
                action: r.action.clone(),
            });
        }
    }

    // Stable, deterministic order: worst severity first, then rule id.
    triggered.sort_by(|a, b| b.severity.cmp(&a.severity).then_with(|| a.id.cmp(&b.id)));

    Validation {
        status: ValidationStatus::from_severity(worst),
        triggered,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::money::Paise;

    fn rules() -> RuleSet {
        RuleSet::embedded()
    }

    #[test]
    fn short_runway_blocks() {
        let s = Snapshot {
            cash: Paise::from_rupees(100_000),
            monthly_burn: Paise::from_rupees(100_000),
            monthly_revenue: Paise::ZERO,
            ..Default::default()
        };
        // runway = 1 month -> TREASURY-001 BLOCK
        let intent = crate::fold::global::fold_global(&s);
        let v = validate(&intent, &s, Some(Domain::Treasury), &rules());
        assert_eq!(v.status, ValidationStatus::Red);
        assert!(v.triggered.iter().any(|t| t.id == "TREASURY-001"));
        // every triggered rule carries a citation
        assert!(v
            .triggered
            .iter()
            .all(|t| !t.statute.is_empty() && !t.section.is_empty()));
    }

    #[test]
    fn healthy_snapshot_is_green() {
        let s = Snapshot {
            cash: Paise::from_rupees(12_000_000),
            monthly_burn: Paise::from_rupees(500_000),
            monthly_revenue: Paise::from_rupees(600_000),
            ..Default::default()
        };
        let intent = crate::fold::global::fold_global(&s);
        let v = validate(&intent, &s, Some(Domain::Treasury), &rules());
        assert_eq!(v.status, ValidationStatus::Green);
        assert!(v.triggered.is_empty());
    }

    #[test]
    fn domain_rules_out_of_scope_do_not_fire() {
        // A GST late-filing metric is present, but we validate the treasury domain only.
        let mut s = Snapshot {
            cash: Paise::from_rupees(12_000_000),
            monthly_burn: Paise::from_rupees(100_000),
            monthly_revenue: Paise::from_rupees(200_000),
            ..Default::default()
        };
        s.metrics.insert("gstr3b_days_late".into(), 5.0);
        let intent = crate::fold::global::fold_global(&s);
        let v = validate(&intent, &s, Some(Domain::Treasury), &rules());
        assert!(v.triggered.iter().all(|t| t.id != "GST-001"));
    }
}
