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
use std::collections::BTreeMap;

/// A claim that a Python-computed figure equals what Mahsa independently recomputes. The live
/// Prime-Directive gate (§0.4): the /fold caller sends these alongside the snapshot, Mahsa
/// recomputes each to the paisa, and a mismatch BLOCKS. An unrecomputable target is left
/// honest-pending (◐), never a block.
///
/// A claim is either **single-value** (`claimed_paise`, e.g. a TDS amount) or **multi-value**
/// (`claimed_values`, a map of named paise, e.g. ITC set-off's per-head cash + remaining credit).
#[derive(Debug, Clone, Deserialize)]
pub struct RecomputeClaim {
    /// Which recompute path (e.g. "tds_on_payment", "itc_setoff").
    pub target: String,
    /// The path's inputs as a JSON object (fields match the recompute fn's arguments).
    #[serde(default)]
    pub inputs: Value,
    /// The figure Maisha (Python) computed, in integer paise (single-value claims).
    #[serde(default)]
    pub claimed_paise: i64,
    /// Named paise figures for a multi-value claim; when present this claim is checked field-wise
    /// (subset match) against the multi-value recompute and `claimed_paise` is ignored.
    #[serde(default)]
    pub claimed_values: Option<BTreeMap<String, i64>>,
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
    /// Recomputed named paise for a multi-value target; `None` for single-value or unrecomputable.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recomputed_values: Option<BTreeMap<String, i64>>,
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
            pf_esi::statutory_wage_base(
                gi(inp, "included"),
                gi(inp, "excluded_addback"),
                gi(inp, "excluded_terminal"),
                gi(inp, "in_kind"),
            )
            .0
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
        "interest_234b" => {
            slab_tax::interest_234b(gi(inp, "assessed_tax"), gi(inp, "advance_paid"), gi(inp, "months"))
        }
        "interest_234c" => {
            let paid: Vec<i64> = inp
                .get("cumulative_paid")
                .and_then(Value::as_array)
                .map(|a| a.iter().map(|v| v.as_i64().unwrap_or(0)).collect())
                .unwrap_or_default();
            slab_tax::interest_234c(gi(inp, "total_liability"), &paid)
        }
        "company_tax_115baa" => slab_tax::company_tax_115baa(gi(inp, "total_income")),
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
                inp.get("fixed_term").and_then(Value::as_bool).unwrap_or(false),
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

/// A GST head triplet [igst, cgst, sgst] read from `inp[key] = {igst, cgst, sgst}`.
fn heads3(inp: &Value, key: &str) -> [i64; 3] {
    let h = inp.get(key);
    let g = |k: &str| h.and_then(|o| o.get(k)).and_then(Value::as_i64).unwrap_or(0);
    [g("igst"), g("cgst"), g("sgst")]
}

/// Recompute a multi-value target — one that yields several named paise figures rather than one.
/// Returns `None` for an unknown/unported target (→ honest-pending).
fn recompute_multi(target: &str, inp: &Value) -> Option<BTreeMap<String, i64>> {
    match target {
        "itc_setoff" => {
            let (cash, rem) = itc::itc_setoff(heads3(inp, "output"), heads3(inp, "credit"));
            let mut m = BTreeMap::new();
            for (i, head) in ["igst", "cgst", "sgst"].iter().enumerate() {
                m.insert(format!("cash_{head}"), cash[i]);
                m.insert(format!("credit_{head}"), rem[i]);
            }
            Some(m)
        }
        _ => None,
    }
}

/// Recompute one claim and compare to the paisa. Multi-value claims (`claimed_values` set) are
/// matched field-wise as a subset — every claimed key must equal its recomputed value.
pub fn check_claim(claim: &RecomputeClaim) -> RecomputeCheck {
    if let Some(want) = &claim.claimed_values {
        let recomputed = recompute_multi(&claim.target, &claim.inputs);
        let (matches, note) = match &recomputed {
            Some(got) => {
                let ok = want.iter().all(|(k, v)| got.get(k) == Some(v));
                if ok {
                    (true, "verified — recomputed to the paisa".to_string())
                } else {
                    (false, format!("MISMATCH — claimed {want:?}, Mahsa recomputed {got:?}"))
                }
            }
            None => (
                false,
                "honest-pending — Mahsa cannot yet independently recompute this target".to_string(),
            ),
        };
        return RecomputeCheck {
            target: claim.target.clone(),
            label: claim.label.clone(),
            claimed_paise: 0,
            recomputed_paise: None,
            recomputed_values: recomputed,
            matches,
            note,
        };
    }

    let recomputed = recompute(&claim.target, &claim.inputs);
    let (matches, note) = match recomputed {
        Some(r) if r == claim.claimed_paise => {
            (true, "verified — recomputed to the paisa".to_string())
        }
        Some(r) => (
            false,
            format!("MISMATCH — Maisha claimed {}, Mahsa recomputed {}", claim.claimed_paise, r),
        ),
        None => (
            false,
            "honest-pending — Mahsa cannot yet independently recompute this target".to_string(),
        ),
    };
    RecomputeCheck {
        target: claim.target.clone(),
        label: claim.label.clone(),
        claimed_paise: claim.claimed_paise,
        recomputed_paise: recomputed,
        recomputed_values: None,
        matches,
        note,
    }
}

pub fn check_claims(claims: &[RecomputeClaim]) -> Vec<RecomputeCheck> {
    claims.iter().map(check_claim).collect()
}

/// A recompute mismatch (recomputable AND wrong) — the Prime-Directive block trigger. An
/// unrecomputable target (nothing recomputed) is honest-pending, never a block.
pub fn has_mismatch(checks: &[RecomputeCheck]) -> bool {
    checks
        .iter()
        .any(|c| (c.recomputed_paise.is_some() || c.recomputed_values.is_some()) && !c.matches)
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
        RecomputeClaim {
            target: target.to_string(),
            inputs,
            claimed_paise: claimed,
            claimed_values: None,
            label: None,
        }
    }

    #[test]
    fn multi_value_itc_setoff_verifies_and_mismatches() {
        // IGST output 5000, IGST credit 8000 -> IGST cash 0, IGST credit remaining 3000.
        let inputs = json!({"output": {"igst": 5000}, "credit": {"igst": 8000}});
        let mut want = std::collections::BTreeMap::new();
        want.insert("cash_igst".to_string(), 0i64);
        want.insert("credit_igst".to_string(), 3000i64);
        let ok = RecomputeClaim {
            target: "itc_setoff".to_string(),
            inputs: inputs.clone(),
            claimed_paise: 0,
            claimed_values: Some(want.clone()),
            label: None,
        };
        let c = check_claim(&ok);
        assert!(c.matches, "{}", c.note);
        assert_eq!(c.recomputed_values.as_ref().unwrap()["cash_igst"], 0);

        // A wrong claimed cash figure is a recomputable mismatch -> blocks.
        want.insert("cash_igst".to_string(), 999);
        let bad = RecomputeClaim { claimed_values: Some(want), ..ok };
        let cb = check_claim(&bad);
        assert!(!cb.matches);
        assert!(has_mismatch(std::slice::from_ref(&cb)));
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
        // ₹60,000 (not ₹50,000): at exactly the threshold the correct answer is now 0, which
        // would make a "wrong claim" test accidentally assert against the no-TDS path.
        let c = check_claim(&claim("tds_on_payment", json!({"section": "194J", "amount": 6000000}), 999999));
        assert!(!c.matches);
        assert_eq!(c.recomputed_paise, Some(600000)); // 10% of ₹60,000
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
        let ok = check_claim(&claim("statutory_wage_base", json!({"included": 3000000, "excluded_addback": 0}), 3000000));
        let wrong = check_claim(&claim("statutory_wage_base", json!({"included": 3000000, "excluded_addback": 0}), 1));
        assert!(!has_mismatch(std::slice::from_ref(&ok)));
        assert!(has_mismatch(&[ok, wrong]));
    }
}
