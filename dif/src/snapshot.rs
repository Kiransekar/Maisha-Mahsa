//! The financial snapshot that fold/validate operate on. This is the *only* input;
//! there is no hidden state. Time is injected via `as_of` — the core never reads a clock.

use crate::money::Paise;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// The 12 domains. `from_str` is used by the HTTP router to classify a request.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Domain {
    Treasury,
    Revenue,
    Payables,
    Payroll,
    Gst,
    Tax,
    Ledger,
    Forecast,
    Equity,
    Compliance,
    Expense,
    Vault,
}

impl Domain {
    pub fn parse(s: &str) -> Option<Domain> {
        Some(match s.to_ascii_lowercase().as_str() {
            "treasury" => Domain::Treasury,
            "revenue" => Domain::Revenue,
            "payables" => Domain::Payables,
            "payroll" => Domain::Payroll,
            "gst" => Domain::Gst,
            "tax" => Domain::Tax,
            "ledger" => Domain::Ledger,
            "forecast" => Domain::Forecast,
            "equity" => Domain::Equity,
            "compliance" => Domain::Compliance,
            "expense" => Domain::Expense,
            "vault" => Domain::Vault,
            _ => return None,
        })
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Domain::Treasury => "treasury",
            Domain::Revenue => "revenue",
            Domain::Payables => "payables",
            Domain::Payroll => "payroll",
            Domain::Gst => "gst",
            Domain::Tax => "tax",
            Domain::Ledger => "ledger",
            Domain::Forecast => "forecast",
            Domain::Equity => "equity",
            Domain::Compliance => "compliance",
            Domain::Expense => "expense",
            Domain::Vault => "vault",
        }
    }
}

/// A point-in-time financial snapshot. Money fields are paise; ratios are `[0,1]`.
/// Domain-specific numbers that don't have a dedicated field go in `metrics`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    /// Injected "as of" date (ISO-8601). The core does not read a clock.
    #[serde(default)]
    pub as_of: String,

    #[serde(default)]
    pub cash: Paise,
    #[serde(default)]
    pub monthly_burn: Paise,
    #[serde(default)]
    pub monthly_revenue: Paise,
    #[serde(default)]
    pub monthly_new_arr: Paise,
    #[serde(default)]
    pub ar_total: Paise,
    #[serde(default)]
    pub ap_total: Paise,
    #[serde(default)]
    pub forex_exposure: Paise,

    /// Number of distinct bank accounts (diversification signal).
    #[serde(default)]
    pub bank_account_count: u32,
    /// Share of total cash in the single largest account, `[0,1]` (concentration).
    #[serde(default)]
    pub largest_account_share: f64,

    /// Statutory filings currently overdue across all domains.
    #[serde(default)]
    pub overdue_filings: u32,
    /// Days until the next statutory filing (negative = already overdue).
    #[serde(default = "default_days")]
    pub days_to_next_filing: i64,

    /// Generic numeric metric bag, keyed by name (e.g. `"itc_claimed_ratio"`).
    /// Rules and domain folds read from here when there is no typed field.
    #[serde(default)]
    pub metrics: BTreeMap<String, f64>,
}

fn default_days() -> i64 {
    9999
}

impl Default for Snapshot {
    fn default() -> Self {
        Snapshot {
            as_of: String::new(),
            cash: Paise::ZERO,
            monthly_burn: Paise::ZERO,
            monthly_revenue: Paise::ZERO,
            monthly_new_arr: Paise::ZERO,
            ar_total: Paise::ZERO,
            ap_total: Paise::ZERO,
            forex_exposure: Paise::ZERO,
            bank_account_count: 0,
            largest_account_share: 0.0,
            overdue_filings: 0,
            days_to_next_filing: default_days(),
            metrics: BTreeMap::new(),
        }
    }
}

impl Snapshot {
    /// Net monthly burn (burn minus revenue), in paise; clamped at zero (profitable → 0).
    pub fn net_burn(&self) -> Paise {
        // saturating: attacker-controlled /fold paise must never overflow (silent wrap in release).
        let net = self.monthly_burn.0.saturating_sub(self.monthly_revenue.0);
        Paise(net.max(0))
    }

    /// Runway in months = cash / net_burn. Returns `f64::INFINITY` when not burning.
    pub fn runway_months(&self) -> f64 {
        let nb = self.net_burn();
        if nb.is_zero() {
            f64::INFINITY
        } else {
            self.cash.rupees() / nb.rupees()
        }
    }

    /// Burn multiple = net burn / net new ARR (lower is better). `INFINITY` if no ARR.
    pub fn burn_multiple(&self) -> f64 {
        if self.monthly_new_arr.is_zero() {
            f64::INFINITY
        } else {
            self.net_burn().rupees() / self.monthly_new_arr.rupees()
        }
    }

    /// Resolve a named metric for rule/fold evaluation. Derived metrics take precedence,
    /// then typed fields, then the `metrics` bag. Unknown names return `None`.
    pub fn metric(&self, key: &str) -> Option<f64> {
        Some(match key {
            "runway_months" => self.runway_months(),
            "burn_multiple" => self.burn_multiple(),
            "cash_rupees" => self.cash.rupees(),
            "net_burn_rupees" => self.net_burn().rupees(),
            "monthly_revenue_rupees" => self.monthly_revenue.rupees(),
            "ar_total_rupees" => self.ar_total.rupees(),
            "ap_total_rupees" => self.ap_total.rupees(),
            "forex_exposure_rupees" => self.forex_exposure.rupees(),
            "bank_account_count" => self.bank_account_count as f64,
            "largest_account_share" => self.largest_account_share,
            "overdue_filings" => self.overdue_filings as f64,
            "days_to_next_filing" => self.days_to_next_filing as f64,
            other => return self.metrics.get(other).copied(),
        })
    }
}

/// HTTP request body for `POST /fold`.
#[derive(Debug, Clone, Deserialize)]
pub struct FoldRequest {
    /// Optional domain hint. If absent, only the global fold runs.
    #[serde(default)]
    pub domain: Option<String>,
    #[serde(default)]
    pub query: Option<String>,
    pub snapshot: Snapshot,
    #[serde(default)]
    pub rules_version: Option<String>,
    /// Prime-Directive claims: figures Maisha computed, for Mahsa to independently recompute
    /// and block on mismatch (§0.4). Empty (the default) preserves the prior /fold behaviour.
    #[serde(default)]
    pub recompute_claims: Vec<crate::recompute::RecomputeClaim>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runway_handles_zero_burn() {
        let s = Snapshot {
            cash: Paise::from_rupees(1000),
            monthly_revenue: Paise::from_rupees(100),
            monthly_burn: Paise::from_rupees(50),
            ..Default::default()
        };
        // revenue > burn -> net burn 0 -> infinite runway
        assert!(s.runway_months().is_infinite());
        assert_eq!(s.net_burn(), Paise::ZERO);
    }

    #[test]
    fn runway_is_cash_over_net_burn() {
        let s = Snapshot {
            cash: Paise::from_rupees(120),
            monthly_burn: Paise::from_rupees(40),
            monthly_revenue: Paise::from_rupees(10),
            ..Default::default()
        };
        // net burn = 30 -> 120/30 = 4 months
        assert_eq!(s.runway_months(), 4.0);
        assert_eq!(s.metric("runway_months"), Some(4.0));
    }

    #[test]
    fn domain_roundtrip() {
        assert_eq!(Domain::parse("GST"), Some(Domain::Gst));
        assert_eq!(Domain::Gst.as_str(), "gst");
        assert_eq!(Domain::parse("bogus"), None);
    }
}
