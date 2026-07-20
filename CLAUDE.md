# Maisha-Mahsa — Build Doctrine (CLAUDE.md)

> **`docs/MASTER_PLAN.md` (MMX-1.0) is the immutable program spec.** Read it at session start.
> Never modify it. Log work to `PROGRESS.md` and mirror status in `PROGRESS_BOARD.md`. Follow §0
> governance — especially §0.4 (no ✓ Verified without Mahsa recomputation) and §0.6 (no invented
> statutory values; source from CA-initialled oracle vectors or a cited primary source).

> This file governs **how** we build. The product spec is
> [`maisha_mahsa_v4_full_suite_prd.md`](./maisha_mahsa_v4_full_suite_prd.md) — that PRD is the
> source of truth for *what* to build. Do not contradict the PRD; if a change is needed,
> amend the PRD explicitly and note it in `BUILD_PROGRESS.md`.

## 1. The Golden Rule (never violate)

**Maisha never talks to the user directly. Mahsa is the gatekeeper.**
Every number the LLM (Maisha, Python) produces is recomputed by Mahsa's deterministic
Rust engine before it reaches a human. Every response is folded → validated → unfolded,
and every decision is written to the hash-chained `audit_log`.

## 2. Zero Error Tolerance

This is a financial-compliance product. A wrong number is a regulatory liability, not a bug.

- **No vacuous passes.** A test that asserts nothing, or is skipped without a tracked reason,
  is treated as a failure. Skips must carry `reason=` and a `BUILD_PROGRESS.md` line.
- **No silent fallbacks.** Money math must be exact: use integer **paise** (1 INR = 100 paise)
  for all amounts inside the core; format to rupees only at the edge. Never use binary floats
  for money in validation logic.
- **Determinism.** Mahsa (Rust) must be pure and reproducible: same input → same output.
  No clocks, no RNG, no network inside fold/validate. Inject time as a parameter.
- **Every rule is cited.** A validation rule without a `statute` + `section` is incomplete.
- **CI gate is binary.** `make verify` (Rust `cargo test` + Python `pytest` + linters) must be
  green before any module is marked ✅ in `BUILD_PROGRESS.md`.

## 3. Bottom-Up Build Order

We build the foundation first and only stack on green layers.

```
L0  Core types & money         → paise arithmetic, IntentVec, ResponseShape  (Rust + Python mirror)
L1  Mahsa DIF engine           → fold / validate / unfold / critic, rules.yaml, property tests
L2  Persistence                → schema.sql (40+ tables), SQLAlchemy models, migrations
L3  Core services              → MahsaClient, DomainRouter, hash-chained AuditLog
L4  Domain modules (×12)       → one vertical slice at a time, each fully tested before the next
L5  Email channel + Web UI     → templates, HTMX dashboard, pixel-level polish
L6  Application integration    → end-to-end, 1-month parallel-run, runbook
```

A layer is "done" only when its unit tests **and** the integration tests that cross into it
are green. Never start L(n+1) work that depends on a red L(n).

## 4. Module Split (unit + integration boundaries)

Each of the 12 PRD domains (`treasury, revenue, payables, payroll, gst, tax, ledger,
forecast, equity, compliance, expense, vault`) is an independently testable module with the
**same contract**:

```
api/app/domains/<domain>/
  __init__.py        # exports the service + manifest
  manifest.py        # feature list + build status (the unit-of-progress)
  models.py          # SQLAlchemy models for this domain only
  schemas.py         # Pydantic v2 request/response models
  service.py         # business logic — subclass of core.domain.BaseDomainService
  router.py          # FastAPI routes (thin; delegates to service)
  rules.py           # domain rule IDs this module owns (mirror of dif/rules)
```

- **Unit tests** (`api/tests/unit/<domain>/`) test `service.py` against an in-memory SQLite,
  no network, Mahsa stubbed. They test the *math and the rules* exhaustively.
- **Integration tests** (`api/tests/integration/`) run the real FastAPI app against a real
  (ephemeral) Mahsa binary over HTTP, exercising the full fold→validate→unfold→audit loop.
- The **Rust side** mirrors this: `dif/src/{fold,validate,intent}/<domain>.rs` with `proptest`
  property tests in `dif/tests/` and HTTP integration tests in `dif/tests/integration.rs`.

## 5. Definition of Done for a domain module

1. `manifest.py` lists every PRD feature for the domain with status `done`.
2. Rust fold sub-vector + validation rules implemented with property tests.
3. Python service implements every feature, exact paise math, full unit coverage.
4. Router wired, HTMX page renders, email template (if any) renders.
5. At least one integration test exercises the domain through the real loop.
6. `make verify` green. `BUILD_PROGRESS.md` row flipped to ✅ with the commit/date.

## 6. Commands

```
make verify      # the gate: rust tests + python tests + lint + type-check
make test-rust   # cargo test (workspace)
make test-py     # pytest (unit + integration)
make lint        # ruff + cargo clippy -D warnings
make dev         # docker-compose up (api + dif + redis + mailhog + ollama)
make fmt         # ruff format + cargo fmt
```

## 7. Conventions

- **Money:** integer paise everywhere internally. Helper: `core.money.Paise`.
- **Dates:** ISO-8601 strings in DB (per PRD schema); parse to `date` at the service edge.
- **IDs / hashes:** SHA-256, lowercase hex. Audit chain: `this_hash = sha256(prev_hash || canonical_json(entry))`.
- **LLM:** local Ollama first; fallback `claude-opus-4-8` / `claude-sonnet-4-6` only when explicitly enabled. Never let the LLM emit a final number that Mahsa hasn't recomputed.
- **UI:** vanilla CSS + HTMX, no build step. Design tokens live in `web/static/css/tokens.css`.
  Pixel-level polish is a requirement, not a nice-to-have — see `skills/ui-polish`.
- **Skills:** project-specific build guides live in `skills/`. Read the relevant one before
  starting a module.

## 8. Where things live

| Concern | Path |
|---|---|
| Product spec (source of truth) | `maisha_mahsa_v4_full_suite_prd.md` |
| Build progress / tracker | `BUILD_PROGRESS.md` |
| Mahsa (Rust DIF core) | `dif/` |
| Maisha (Python service) | `api/` |
| Infra (compose, Caddy) | `infra/` |
| Build skills | `skills/` |
