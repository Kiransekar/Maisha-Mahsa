//! Independent statutory recomputation (MMX-1.0 §WS3.1) — Mahsa re-derives, in Rust, the
//! figures the Python service produces, so no number reaches a human unrecomputed (Prime
//! Directive §0.4). Pure, clock-free, integer paise; every fn mirrors one Python path exactly.
//!
//! Parity is proven by `tests/parity.rs`, which replays the SAME CA-oracle vectors
//! (`api/tests/statutory_oracle/vectors/*.yaml`) against these fns and asserts equality to the
//! paisa. Because the Python oracle asserts the same vectors, Rust == expected == Python.
//!
//! Port order (§WS3.1): slab tax → PF/ESI (+ s.2(y) wage base) → TDS (all sections) →
//! ITC set-off → GST late-fee/interest → gratuity/bonus.

pub mod slab_tax;
pub mod pf_esi;
pub mod tds;
pub mod itc;
pub mod gst_fees;
pub mod gratuity_bonus;

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// A claim that a Python-computed figure equals what Mahsa independently recomputes. The live
/// Prime-Directive gate (§0.4): the /fold caller sends these alongside the snapshot, Mahsa
/// recomputes each to the paisa, and a mismatch BLOCKS. An unrecomputable target is left
/// honest-pending (◐), never a block.
#[derive(Debug, Clone, Deserialize)]
pub struct RecomputeClaim {
    /// Which recompute path (e.g. "tds_on_payment", "esi_employee", "gratuity_hybrid").
    pub target: String,
    /// The path's inputs as a JSON object (fields match the recompute fn's arguments).
    #[serde(default)]
    pub inputs: Value,
    /// The figure Maisha (Python) computed, in integer paise.
    pub claimed_paise: i64,
    /// Optional human label for the figure, surfaced in the block diagnostic / badges.
    #[serde(default)]
    pub label: Option<String>,
}

/// Outcome of recomputing one claim.
#[derive(Debug, Clone, Serialize)]
pub struct RecomputeCheck {
    pub target: String,
    pub label: Option<String>,
    pub claimed_paise: i64,
    /// `None` when Mahsa cannot recompute this target (unknown/unported) → honest-pending.
    pub recomputed_paise: Option<i64>,
    /// True only when the target is recomputable AND matches the claim to the paisa.
    pub matches: bool,
    pub note: String,
}

fn gi(v: &Value, key: &str) -> i64 {
    v.get(key).and_then(Value::as_i64).unwrap_or(0)
}
fn gs<'a>(v: &'a Value, key: &str) -> Option<&'a str> {
    v.get(key).and_then(Value::as_str)
}
fn ymd(v: &Value, key: &str) -> Option<gratuity_bonus::Ymd> {
    let s = gs(v, key)?;
    let p: Vec<&str> = s.split('-').collect();
    if p.len() != 3 {
        return None;
    }
    Some((p[0].parse().ok()?, p[1].parse().ok()?, p[2].parse().ok()?))
}

/// Recompute a single target from JSON inputs. Returns `None` for an unknown/unported target
/// (→ honest-pending), so the caller can distinguish "cannot verify" from "verified wrong".
fn recompute(target: &str, inp: &Value) -> Option<i64> {
    Some(match target {
        "statutory_wage_base" => {
            pf_esi::statutory_wage_base(gi(inp, "included"), gi(inp, "excluded"), gi(inp, "in_kind")).0
        }
        "esi_employee" => {
            let (emp, _) = pf_esi::esi(gi(inp, "gross_monthly"));
            emp.0
        }
        "esi_employer" => {
            let (_, empr) = pf_esi::esi(gi(inp, "gross_monthly"));
            empr.0
        }
        "pf_employee" => pf_esi::pf_employee(gi(inp, "basic_monthly")).0,
        "pf_employer" => pf_esi::pf_employer(gi(inp, "basic_monthly")).0,
        "eps_employer" => pf_esi::eps_employer(gi(inp, "basic_monthly")).0,
        "annual_income_tax" => slab_tax::annual_income_tax(gi(inp, "annual_taxable")).0,
        "late_fee_234e" => slab_tax::late_fee_234e(gi(inp, "days_late"), gi(inp, "tds_amount")),
        "tds_on_payment" => {
            let ytd = inp.get("aggregate_ytd").and_then(Value::as_i64).unwrap_or(0);
            tds::tds_on_payment(
                gs(inp, "section")?,
                gi(inp, "amount"),
                gs(inp, "payee_type").unwrap_or("company"),
                gs(inp, "category"),
                ytd,
            )
                .tds_paise
                .0
        }
        "gratuity_hybrid" => {
            gratuity_bonus::gratuity_hybrid(
                ymd(inp, "doj")?,
                ymd(inp, "exit_date")?,
                ymd(inp, "boundary")?,
                gi(inp, "old_base"),
                gi(inp, "new_base"),
            )
            .0
        }
        "gratuity_required" => {
            gratuity_bonus::gratuity_required(gi(inp, "last_basic_monthly"), gi(inp, "completed_years")).0
        }
        "bonus_provision_monthly" => gratuity_bonus::bonus_provision_monthly(gi(inp, "basic_monthly")).0,
        "late_fee_3b" => {
            gst_fees::late_fee_3b(gi(inp, "days_late"), inp.get("is_nil").and_then(Value::as_bool).unwrap_or(false))
        }
        "interest_3b" => gst_fees::interest_3b(gi(inp, "cash_tax"), gi(inp, "days_late")),
        _ => return None,
    })
}

/// Recompute one claim and compare to the paisa.
pub fn check_claim(claim: &RecomputeClaim) -> RecomputeCheck {
    let recomputed = recompute(&claim.target, &claim.inputs);
    let (matches, note) = match recomputed {
        Some(r) if r == claim.claimed_paise => (true, "verified — recomputed to the paisa".to_string()),
        Some(r) => (
            false,
            format!("MISMATCH — Maisha claimed {}, Mahsa recomputed {}", claim.claimed_paise, r),
        ),
        None => (false, "honest-pending — Mahsa cannot yet independently recompute this target".to_string()),
    };
    RecomputeCheck {
        target: claim.target.clone(),
        label: claim.label.clone(),
        claimed_paise: claim.claimed_paise,
        recomputed_paise: recomputed,
        matches,
        note,
    }
}

pub fn check_claims(claims: &[RecomputeClaim]) -> Vec<RecomputeCheck> {
    claims.iter().map(check_claim).collect()
}

/// A recompute mismatch (recomputable AND wrong) — the Prime-Directive block trigger. An
/// unrecomputable target (`recomputed_paise` is `None`) is honest-pending, never a block.
pub fn has_mismatch(checks: &[RecomputeCheck]) -> bool {
    checks.iter().any(|c| c.recomputed_paise.is_some() && !c.matches)
}

/// Round integer paise to the nearest whole rupee, half up (mirror of Python `_round_rupee`).
pub(crate) fn round_rupee(paise: i64) -> i64 {
    if paise >= 0 {
        ((paise + 50) / 100) * 100
    } else {
        -(((-paise) + 50) / 100) * 100
    }
}

/// Round non-negative integer paise UP to the next whole rupee (mirror of Python `_ceil_rupee`
/// applied to an already-integer paise amount).
pub(crate) fn ceil_rupee(paise: i64) -> i64 {
    debug_assert!(paise >= 0);
    ((paise + 99) / 100) * 100
}

#[cfg(test)]
mod claim_tests {
    use super::*;
    use serde_json::json;

    fn claim(target: &str, inputs: Value, claimed: i64) -> RecomputeClaim {
        RecomputeClaim { target: target.to_string(), inputs, claimed_paise: claimed, label: None }
    }

    #[test]
    fn correct_claim_verifies() {
        // ESI employee on gross ₹20,001 = ₹151 (15100 paise), matching the oracle vector.
        let c = check_claim(&claim("esi_employee", json!({"gross_monthly": 2000100}), 15100));
        assert!(c.matches);
        assert_eq!(c.recomputed_paise, Some(15100));
    }

    #[test]
    fn wrong_claim_is_a_mismatch() {
        let c = check_claim(&claim("tds_on_payment", json!({"section": "194J", "amount": 5000000}), 999999));
        assert!(!c.matches);
        assert_eq!(c.recomputed_paise, Some(500000)); // 10% of ₹50,000
        assert!(c.note.contains("MISMATCH"));
    }

    #[test]
    fn unknown_target_is_honest_pending_not_a_mismatch() {
        let c = check_claim(&claim("itr_computation", json!({}), 123));
        assert!(!c.matches);
        assert_eq!(c.recomputed_paise, None);
        assert!(!has_mismatch(std::slice::from_ref(&c))); // None recompute must NOT block
    }

    #[test]
    fn has_mismatch_only_on_recomputable_wrong() {
        let ok = check_claim(&claim("statutory_wage_base", json!({"included": 3000000, "excluded": 0}), 3000000));
        let wrong = check_claim(&claim("statutory_wage_base", json!({"included": 3000000, "excluded": 0}), 1));
        assert!(!has_mismatch(std::slice::from_ref(&ok)));
        assert!(has_mismatch(&[ok, wrong]));
    }
}
