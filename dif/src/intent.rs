//! The hierarchical Intent IR: one global 8-dim vector + per-domain 8-dim sub-vectors.
//!
//! Every dimension is a **health** score in `[0.0, 1.0]` where `1.0` is healthy.
//! (e.g. `risk_exposure` = 1.0 means *low* risk.) This convention is uniform so the
//! unfold layer can treat any dimension the same way.

use serde::{Deserialize, Serialize};

/// The 8 global dimensions, in fixed order. Index stability is part of the API.
pub const GLOBAL_DIMS: [&str; 8] = [
    "cash_flow",
    "risk_exposure",
    "liquidity",
    "tax_efficiency",
    "compliance",
    "diversification",
    "currency_hedge",
    "growth",
];

/// Per-domain sub-vector dimension labels (from PRD §2.2). Index order is the API.
pub fn domain_dims(domain: &str) -> Option<[&'static str; 8]> {
    Some(match domain {
        "payroll" => [
            "pf_compliance",
            "esi_compliance",
            "tds_accuracy",
            "pt_state",
            "lwf_state",
            "gratuity_reserve",
            "bonus_reserve",
            "leave_liability",
        ],
        "gst" => [
            "filing_timeliness",
            "itc_optimization",
            "e_invoice_readiness",
            "hsn_accuracy",
            "rcm_compliance",
            "lut_validity",
            "reconciliation_gap",
            "penalty_exposure",
        ],
        "tax" => [
            "advance_tax_coverage",
            "tds_deposit_timeliness",
            "as26_match",
            "audit_trigger",
            "mat_exposure",
            "holiday_utilization",
            "tp_documentation",
            "itr_accuracy",
        ],
        "treasury" => [
            "runway_months",
            "burn_stability",
            "cash_concentration",
            "fd_exposure",
            "forex_exposure",
            "credit_line_utilization",
            "sweep_efficiency",
            "liquidity_stress",
        ],
        "revenue" => [
            "ar_turnover",
            "dunning_effectiveness",
            "credit_risk",
            "revenue_quality",
            "deferred_revenue",
            "export_ratio",
            "irn_coverage",
            "customer_concentration",
        ],
        "payables" => [
            "ap_turnover",
            "msme_compliance",
            "tds_deposit_status",
            "po_coverage",
            "early_pay_discount_capture",
            "vendor_concentration",
            "recurring_spend",
            "dispute_rate",
        ],
        "equity" => [
            "dilution_rate",
            "esop_utilization",
            "safe_conversion_complexity",
            "investor_reporting_timeliness",
            "dividend_capacity",
            "share_pricing_fairness",
            "board_compliance",
            "cap_table_accuracy",
        ],
        "compliance" => [
            "roc_filing_status",
            "gst_filing_status",
            "tds_filing_status",
            "pf_filing_status",
            "esi_filing_status",
            "pt_filing_status",
            "secretarial_score",
            "audit_readiness",
        ],
        _ => return None,
    })
}

/// An 8-dim intent vector. Values are clamped to `[0,1]` on construction via `clamped`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct IntentVec(pub [f64; 8]);

impl IntentVec {
    pub const fn zeros() -> Self {
        IntentVec([0.0; 8])
    }

    /// Clamp every component into `[0,1]`. Idempotent.
    pub fn clamped(mut self) -> Self {
        for v in self.0.iter_mut() {
            *v = v.clamp(0.0, 1.0);
        }
        self
    }

    /// True iff every component is within `[0,1]`.
    pub fn is_normalized(&self) -> bool {
        self.0.iter().all(|v| (0.0..=1.0).contains(v))
    }

    /// Lookup a global dimension by name.
    pub fn global(&self, name: &str) -> Option<f64> {
        GLOBAL_DIMS
            .iter()
            .position(|d| *d == name)
            .map(|i| self.0[i])
    }

    /// Blend `self` toward `other` by weight `w_other` (e.g. domain fold blends in
    /// 20% global influence: `domain.blend(global, 0.20)`). Result is clamped.
    pub fn blend(self, other: IntentVec, w_other: f64) -> IntentVec {
        let w = w_other.clamp(0.0, 1.0);
        let mut out = [0.0; 8];
        for (i, o) in out.iter_mut().enumerate() {
            *o = self.0[i] * (1.0 - w) + other.0[i] * w;
        }
        IntentVec(out).clamped()
    }

    /// Mean health across all 8 dimensions — used as a 0..100 domain score.
    pub fn score(&self) -> f64 {
        let m = self.0.iter().sum::<f64>() / 8.0;
        (m * 100.0).clamp(0.0, 100.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_is_idempotent_and_bounded() {
        let v = IntentVec([2.0, -1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]).clamped();
        assert!(v.is_normalized());
        assert_eq!(v.clamped(), v);
        assert_eq!(v.0[0], 1.0);
        assert_eq!(v.0[1], 0.0);
    }

    #[test]
    fn global_lookup_matches_index() {
        let v = IntentVec([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]);
        assert_eq!(v.global("cash_flow"), Some(0.1));
        assert_eq!(v.global("growth"), Some(0.8));
        assert_eq!(v.global("nope"), None);
    }

    #[test]
    fn every_domain_has_eight_unique_dims() {
        for d in [
            "payroll",
            "gst",
            "tax",
            "treasury",
            "revenue",
            "payables",
            "equity",
            "compliance",
        ] {
            let dims = domain_dims(d).unwrap();
            let mut seen = dims.to_vec();
            seen.sort_unstable();
            seen.dedup();
            assert_eq!(seen.len(), 8, "domain {d} must have 8 unique dims");
        }
        assert!(domain_dims("nonexistent").is_none());
    }
}
