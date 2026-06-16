//! The rule model. Rules are **data**, loaded from YAML (CA-signed), never code. Each
//! rule is a set of conditions AND-ed together; if all hold, the rule triggers. Every
//! rule must cite a statute + section (enforced by `RuleSet::validate`).

use crate::intent::IntentVec;
use crate::snapshot::Snapshot;
use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Op {
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
}

impl Op {
    fn apply(self, lhs: f64, rhs: f64) -> bool {
        match self {
            Op::Lt => lhs < rhs,
            Op::Le => lhs <= rhs,
            Op::Gt => lhs > rhs,
            Op::Ge => lhs >= rhs,
            Op::Eq => (lhs - rhs).abs() < f64::EPSILON,
            Op::Ne => (lhs - rhs).abs() >= f64::EPSILON,
        }
    }
}

/// Severity ordering matters: `Block` > `Warning` > `Info`. Declaration order = `Ord`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Info,
    Warning,
    Block,
}

/// One condition. `metric` is either a `Snapshot` metric name, or `intent:<dim>` to read
/// a global intent dimension.
#[derive(Debug, Clone, Deserialize)]
pub struct Condition {
    pub metric: String,
    pub op: Op,
    pub value: f64,
}

impl Condition {
    /// Resolve the metric's current value. `None` if the metric can't be resolved.
    fn resolve(&self, intent: &IntentVec, snap: &Snapshot) -> Option<f64> {
        if let Some(dim) = self.metric.strip_prefix("intent:") {
            intent.global(dim)
        } else {
            snap.metric(&self.metric)
        }
    }

    /// Evaluate. An unresolvable metric makes the condition **false** (so a rule never
    /// fires on missing data) — load-time `RuleSet::validate` guards against typos.
    fn holds(&self, intent: &IntentVec, snap: &Snapshot) -> bool {
        match self.resolve(intent, snap) {
            Some(v) => self.op.apply(v, self.value),
            None => false,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Rule {
    pub id: String,
    pub domain: String,
    pub description: String,
    pub statute: String,
    pub section: String,
    pub severity: Severity,
    #[serde(default)]
    pub all_of: Vec<Condition>,
    #[serde(default)]
    pub action: String,
}

impl Rule {
    /// True iff every condition holds (empty condition list never triggers).
    pub fn triggers(&self, intent: &IntentVec, snap: &Snapshot) -> bool {
        !self.all_of.is_empty() && self.all_of.iter().all(|c| c.holds(intent, snap))
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct RuleSet {
    pub version: String,
    pub rules: Vec<Rule>,
}

impl RuleSet {
    /// Parse a rule set from YAML text.
    pub fn from_yaml(text: &str) -> Result<RuleSet, String> {
        let set: RuleSet = serde_yaml::from_str(text).map_err(|e| e.to_string())?;
        set.validate()?;
        Ok(set)
    }

    /// Structural integrity: unique ids, non-empty citations, at least one condition.
    pub fn validate(&self) -> Result<(), String> {
        let mut seen = std::collections::BTreeSet::new();
        for r in &self.rules {
            if !seen.insert(r.id.clone()) {
                return Err(format!("duplicate rule id: {}", r.id));
            }
            if r.statute.trim().is_empty() || r.section.trim().is_empty() {
                return Err(format!("rule {} missing statute/section citation", r.id));
            }
            if r.all_of.is_empty() {
                return Err(format!("rule {} has no conditions", r.id));
            }
        }
        Ok(())
    }

    /// The embedded, version-controlled default rule set (always available, even with no FS).
    pub fn embedded() -> RuleSet {
        RuleSet::from_yaml(include_str!("../../rules/rules.yaml"))
            .expect("embedded rules.yaml must be valid")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_rules_are_valid_and_nonempty() {
        let rs = RuleSet::embedded();
        assert!(!rs.rules.is_empty());
        rs.validate().unwrap();
    }

    #[test]
    fn duplicate_ids_rejected() {
        let yaml = r#"
version: "test"
rules:
  - { id: A, domain: treasury, description: d, statute: s, section: "1", severity: block, all_of: [{metric: runway_months, op: lt, value: 3}] }
  - { id: A, domain: treasury, description: d, statute: s, section: "1", severity: block, all_of: [{metric: runway_months, op: lt, value: 3}] }
"#;
        assert!(RuleSet::from_yaml(yaml).is_err());
    }

    #[test]
    fn missing_citation_rejected() {
        let yaml = r#"
version: "test"
rules:
  - { id: A, domain: treasury, description: d, statute: "", section: "", severity: block, all_of: [{metric: runway_months, op: lt, value: 3}] }
"#;
        assert!(RuleSet::from_yaml(yaml).is_err());
    }
}
