---
name: rust-dif-core
description: How to work on Mahsa, the Rust DIF sidecar (dif/) — adding a domain fold, extending the intent vectors, the validator, unfold/ResponseShape, and the HTTP surface. Use for any change under dif/. Enforces determinism, exact money, and the property-test discipline.
---

# Working on Mahsa (the Rust DIF core)

Mahsa is the gatekeeper: pure, deterministic, fast (~50–100µs/call). It must never read a
clock, RNG, or do IO inside fold/validate/unfold — `as_of` is injected via the `Snapshot`.

## Module map (`dif/src/`)
- `money.rs` — `Paise` integer money. Never `f64` for money.
- `intent.rs` — `IntentVec` (8-dim, health in `[0,1]`), global + per-domain dim labels.
- `snapshot.rs` — `Snapshot` (typed fields + `metrics` bag), `Domain`, `FoldRequest`. The
  `Snapshot::metric(name)` resolver is what rules read.
- `fold/` — `global.rs` (always runs) + one file per domain; `mod.rs::domain_fold` dispatches
  and blends 20% global influence into a domain sub-vector.
- `validate/` — `rules.rs` (rule model + YAML load + integrity checks) and `mod.rs`
  (hierarchical validator → `ValidationStatus`).
- `unfold.rs` — builds `ResponseShape` (color, banners w/ citations, requires_approval).
- `app.rs` / `main.rs` — axum router (`GET /health`, `POST /fold`) and bootstrap.

## Add a domain fold
1. Create `dif/src/fold/<domain>.rs` with `pub fn fold_<domain>(s: &Snapshot) -> IntentVec`.
   Read typed fields and `metric_or(s, "<name>", default)` for the rest. Return `.clamped()`.
2. `pub mod <domain>;` in `fold/mod.rs`; add a `Domain::<X> => Some(<domain>::fold_<domain>(s).blend(global, 0.20))` arm.
3. Use the dimension order from `intent::domain_dims("<domain>")` — it is the public API.

## Invariants (the property tests in `dif/tests/prop.rs` enforce these)
- Every intent dimension stays in `[0,1]` for any snapshot.
- Folding is deterministic: same input → identical output.
- `Red` status implies at least one `block`-severity rule fired.
Add cases to `prop.rs` for new folds; keep `validation_is_total` honest.

## Gate
```bash
cd dif && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt
```
Clippy is `-D warnings` (zero warnings). Format with `cargo fmt` before committing.

Rules themselves are data — see `skills/indian-fin-rules`.
