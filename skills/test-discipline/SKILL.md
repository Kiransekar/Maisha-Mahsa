---
name: test-discipline
description: The testing standard for Maisha-Mahsa — unit vs integration boundaries, the zero-error gate, property tests, and the no-vacuous-pass / no-silent-skip rules. Use when writing or reviewing any test, or when deciding whether a module is "done".
---

# Test discipline (zero error tolerance)

A wrong number here is a regulatory liability. Tests are how we earn the right to call a
module done. `make verify` is the only definition of done.

## The two boundaries
- **Unit** (`api/tests/unit/<domain>/`, Rust `#[cfg(test)]` + `dif/tests/prop.rs`):
  test the *math and the rules* in isolation. In-memory SQLite, no network, Mahsa not
  involved (or its pure functions called directly). Exhaustive: every threshold, every
  rounding edge, every branch. Money assertions in exact paise.
- **Integration** (`api/tests/integration/`): exercise the **real loop** — `run_loop`
  builds a snapshot, calls the **real Mahsa binary** over HTTP (the `mahsa_server` fixture
  spawns `dif/target/debug/mahsa`), validates, and seals an audit entry. Assert the
  traffic-light status, the cited rule fired, and the audit chain verifies.

## Property tests (Rust)
Encode invariants, not examples: intent dims always in `[0,1]`; fold deterministic; `Red`
implies a `block` rule fired. Add cases when you add a fold. See `dif/tests/prop.rs`.

## Non-negotiable rules
- **No vacuous passes.** Every test asserts a meaningful outcome. A test with no `assert`
  is a failure.
- **No silent skips.** A skip must carry a `reason=` and a line in `BUILD_PROGRESS.md`. The
  only sanctioned skip is the integration suite when the Mahsa binary isn't built — and the
  fix is `cargo build` in `dif/`, not ignoring it.
- **Determinism.** Inject `as_of`/timestamps; never assert against the wall clock.
- **Exactness.** Use `Paise.from_rupees(...)` in expectations; never compare floats for money.

## Run it
```bash
make verify                          # everything
cd dif && cargo test                 # rust unit + property + http integration
cd api && .venv/bin/pytest -q        # python unit + integration
cd api && .venv/bin/pytest -m integration   # just the real-loop tests
```
Before flipping a `BUILD_PROGRESS.md` row to ✅, run `make verify` and paste nothing less
than a fully green result.
