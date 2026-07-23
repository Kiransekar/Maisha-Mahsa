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
    /// Staged-rollout channel (WS1.E3), set from the pack manifest at verified load
    /// ("stable" default = current pack for all tenants). Tenant-visible via `/health`.
    #[serde(default = "default_channel")]
    pub channel: String,
}

fn default_channel() -> String {
    "stable".to_string()
}

/// Rule-pack manifest (WS1.E3): binds the pack `version` to a sha256 of the exact rules.yaml
/// bytes. Integrity is sha256; signing beyond that (Ed25519) is a documented OWNER-STEP
/// (docs/RULE_PACK_SLA.md) — the repo holds no signing keys.
#[derive(Debug, Clone, Deserialize)]
pub struct Manifest {
    pub version: String,
    pub rules_sha256: String,
    #[serde(default = "default_channel")]
    pub channel: String,
}

impl Manifest {
    pub fn from_yaml(text: &str) -> Result<Manifest, String> {
        serde_yaml::from_str(text).map_err(|e| e.to_string())
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
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

    /// WS1.E3 verified load: the pack is accepted only when sha256(rules bytes) and `version`
    /// both match the manifest. Any mismatch is a hard error — fail loud at boot, never serve
    /// a drifted pack.
    pub fn load_verified(rules_text: &str, manifest_text: &str) -> Result<RuleSet, String> {
        let manifest = Manifest::from_yaml(manifest_text)?;
        let digest = sha256_hex(rules_text.as_bytes());
        if digest != manifest.rules_sha256 {
            return Err(format!(
                "rule-pack integrity failure: sha256 of rules is {digest} but the manifest \
                 declares {} — the pack bytes and manifest have drifted",
                manifest.rules_sha256
            ));
        }
        let mut set = RuleSet::from_yaml(rules_text)?;
        if set.version != manifest.version {
            return Err(format!(
                "rule-pack version mismatch: rules.yaml says {} but the manifest says {}",
                set.version, manifest.version
            ));
        }
        set.channel = manifest.channel;
        Ok(set)
    }

    /// The embedded, version-controlled default rule set (always available, even with no FS),
    /// verified against its embedded manifest (WS1.E3).
    pub fn embedded() -> RuleSet {
        RuleSet::load_verified(
            include_str!("../../rules/rules.yaml"),
            include_str!("../../rules/MANIFEST.yaml"),
        )
        .expect("embedded rule pack failed manifest verification")
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

    // ---- WS1.E3: pack manifest verification --------------------------------------------

    const PACK: &str = include_str!("../../rules/rules.yaml");
    const MANIFEST: &str = include_str!("../../rules/MANIFEST.yaml");

    #[test]
    fn verified_load_accepts_the_shipped_pack_and_carries_the_channel() {
        let rs = RuleSet::load_verified(PACK, MANIFEST).unwrap();
        assert_eq!(rs.version, Manifest::from_yaml(MANIFEST).unwrap().version);
        assert_eq!(rs.channel, "stable");
        assert!(!rs.rules.is_empty());
    }

    #[test]
    fn verified_load_rejects_drifted_pack_bytes() {
        // One flipped byte in the pack must fail integrity, loudly naming the mismatch.
        let tampered = PACK.replacen("severity: block", "severity: info", 1);
        assert_ne!(tampered, PACK, "mutation must actually change the pack");
        let err = RuleSet::load_verified(&tampered, MANIFEST).unwrap_err();
        assert!(err.contains("integrity"), "unexpected error: {err}");
    }

    #[test]
    fn verified_load_rejects_version_mismatch() {
        // Correct the sha so ONLY the version disagrees — proves the version check is separate.
        let manifest = format!(
            "pack: in-core\nversion: \"9999.99.9\"\nrules_sha256: \"{}\"\n",
            sha256_hex(PACK.as_bytes())
        );
        let err = RuleSet::load_verified(PACK, &manifest).unwrap_err();
        assert!(err.contains("version mismatch"), "unexpected error: {err}");
    }

    #[test]
    fn rollback_previous_pack_loads_verified_and_the_engine_computes_with_it() {
        // WS1.E3 rollback: the archived previous pack (as MAHSA_RULES would pin it) loads
        // through the same verified path and its rules actually evaluate — the pre-sweep
        // PAYROLL-001 still cites the repealed Act as primary, proving the OLD pack is live.
        let rs = RuleSet::load_verified(
            include_str!("../../rules/archive/rules-2026.07.1.yaml"),
            include_str!("../../rules/archive/MANIFEST-2026.07.1.yaml"),
        )
        .unwrap();
        assert_eq!(rs.version, "2026.07.1");
        assert_eq!(rs.channel, "archived");
        let pf = rs.rules.iter().find(|r| r.id == "PAYROLL-001").unwrap();
        assert_eq!(pf.statute, "EPF & MP Act 1952"); // the archived pack's pre-sweep citation
                                                     // The engine computes with the old pack: PAYROLL-001 triggers on overdue PF.
        let mut snap = Snapshot::default();
        snap.metrics.insert("pf_days_overdue".to_string(), 3.0);
        let intent = IntentVec::zeros();
        assert!(pf.triggers(&intent, &snap));
        snap.metrics.insert("pf_days_overdue".to_string(), 0.0);
        assert!(!pf.triggers(&intent, &snap));
    }
}
