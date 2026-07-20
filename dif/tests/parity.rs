//! Cross-language parity gate (MMX-1.0 §WS3.1/§WS3.2, Prime Directive §0.4).
//!
//! Replays the shared CA-oracle vectors (`api/tests/statutory_oracle/vectors/*.yaml`) against
//! Mahsa's Rust `recompute` fns and asserts equality to the paisa. The Python oracle asserts the
//! same vectors against the same `expected`, so a green run here proves Rust == expected ==
//! Python for every ported path — no FFI needed.
//!
//! Targets not yet ported to Rust are reported explicitly as coverage gaps (never silently
//! skipped): an honest WS3.5-style report of what Mahsa cannot yet independently recompute.

use mahsa::money::Paise;
use mahsa::recompute::{gratuity_bonus, pf_esi, slab_tax, tds};
use serde_yaml::Value;
use std::collections::BTreeSet;
use std::fs;

fn vectors_dir() -> String {
    format!("{}/../api/tests/statutory_oracle/vectors", env!("CARGO_MANIFEST_DIR"))
}

fn load_all() -> Vec<Value> {
    let mut out = Vec::new();
    let dir = vectors_dir();
    for entry in fs::read_dir(&dir).unwrap_or_else(|e| panic!("read {dir}: {e}")) {
        let path = entry.unwrap().path();
        if path.extension().and_then(|s| s.to_str()) != Some("yaml") {
            continue;
        }
        let text = fs::read_to_string(&path).unwrap();
        let items: Vec<Value> = serde_yaml::from_str(&text).unwrap_or_default();
        out.extend(items);
    }
    out
}

fn i(v: &Value, key: &str) -> i64 {
    v.get(key).and_then(Value::as_i64).unwrap_or_else(|| panic!("missing int {key} in {v:?}"))
}
fn i_or(v: &Value, key: &str, default: i64) -> i64 {
    v.get(key).and_then(Value::as_i64).unwrap_or(default)
}
fn ymd(v: &Value, key: &str) -> (i32, u32, u32) {
    let s = v.get(key).and_then(Value::as_str).unwrap();
    let p: Vec<&str> = s.split('-').collect();
    (p[0].parse().unwrap(), p[1].parse().unwrap(), p[2].parse().unwrap())
}

const INCLUDED_KEYS: [&str; 3] = ["basic", "da", "retaining_allowance"];

// The targets Rust recomputes so far (§WS3.1 port order).
const PORTED: [&str; 5] =
    ["esi", "statutory_wage_base", "tds_on_payment", "gratuity_hybrid", "late_fee_234e"];

#[test]
fn rust_matches_oracle_vectors_to_the_paisa() {
    let vectors = load_all();
    assert!(!vectors.is_empty(), "no oracle vectors loaded — parity gate must never be empty");

    let mut failures: Vec<String> = Vec::new();
    let mut covered = 0usize;
    let mut uncovered: BTreeSet<String> = BTreeSet::new();

    for v in &vectors {
        let target = match v.get("target").and_then(Value::as_str) {
            Some(t) => t,
            None => continue,
        };
        let id = v.get("id").and_then(Value::as_str).unwrap_or("?");
        if !PORTED.contains(&target) {
            uncovered.insert(target.to_string());
            continue;
        }
        let inputs = v.get("inputs").unwrap();
        let expected = v.get("expected").unwrap();
        covered += 1;

        match target {
            "esi" => {
                let (emp, empr) = pf_esi::esi(i(inputs, "gross_monthly"));
                let want = expected.as_sequence().unwrap();
                let we = want[0].as_i64().unwrap();
                let wr = want[1].as_i64().unwrap();
                if emp.0 != we || empr.0 != wr {
                    failures.push(format!("{id} esi: got ({},{}) want ({we},{wr})", emp.0, empr.0));
                }
            }
            "statutory_wage_base" => {
                let comps = inputs.get("components").unwrap().as_mapping().unwrap();
                let mut included = 0i64;
                let mut excluded = 0i64;
                for (k, val) in comps {
                    let key = k.as_str().unwrap_or("");
                    let amt = val.as_i64().unwrap_or(0);
                    if INCLUDED_KEYS.contains(&key) {
                        included += amt;
                    } else {
                        excluded += amt;
                    }
                }
                let in_kind = i_or(inputs, "in_kind", 0);
                let got = pf_esi::statutory_wage_base(included, excluded, in_kind);
                let want = expected.as_i64().unwrap();
                if got.0 != want {
                    failures.push(format!("{id} wage_base: got {} want {want}", got.0));
                }
            }
            "tds_on_payment" => {
                let section = inputs.get("section").and_then(Value::as_str).unwrap();
                let amount = i(inputs, "amount");
                let payee = inputs.get("payee_type").and_then(Value::as_str).unwrap_or("company");
                let category = inputs.get("category").and_then(Value::as_str);
                let ytd = i_or(inputs, "aggregate_ytd", 0);
                let got = tds::tds_on_payment(section, amount, payee, category, ytd);
                let want_appl = expected.get("applicable").and_then(Value::as_bool).unwrap();
                let want_tds = expected.get("tds_paise").and_then(Value::as_i64).unwrap();
                if got.applicable != want_appl || got.tds_paise != Paise(want_tds) {
                    failures.push(format!(
                        "{id} tds: got ({},{}) want ({want_appl},{want_tds})",
                        got.applicable, got.tds_paise.0
                    ));
                }
            }
            "gratuity_hybrid" => {
                let got = gratuity_bonus::gratuity_hybrid(
                    ymd(inputs, "doj"),
                    ymd(inputs, "exit_date"),
                    ymd(inputs, "boundary"),
                    i(inputs, "old_base"),
                    i(inputs, "new_base"),
                );
                let want = expected.as_i64().unwrap();
                if got.0 != want {
                    failures.push(format!("{id} gratuity_hybrid: got {} want {want}", got.0));
                }
            }
            "late_fee_234e" => {
                let got = slab_tax::late_fee_234e(i(inputs, "days_late"), i(inputs, "tds_amount"));
                let want = expected.as_i64().unwrap();
                if got != want {
                    failures.push(format!("{id} late_fee_234e: got {got} want {want}"));
                }
            }
            _ => unreachable!(),
        }
    }

    // Honest coverage report (§WS3.5): what Mahsa cannot yet independently recompute.
    eprintln!("parity: {covered} vector(s) checked against Rust recompute.");
    if !uncovered.is_empty() {
        eprintln!("parity COVERAGE GAP — targets not yet ported to Rust: {uncovered:?}");
    }

    assert!(covered > 0, "no ported vectors exercised — parity gate is vacuous");
    assert!(failures.is_empty(), "Rust↔oracle parity mismatches:\n{}", failures.join("\n"));
}
