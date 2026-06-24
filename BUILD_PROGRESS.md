# Maisha-Mahsa — Build Progress

Living tracker. The PRD is the spec; this file is the truth of *what is actually built & green*.
A row flips to ✅ only when `make verify` is green for it (see `CLAUDE.md` §5).

Legend: ✅ done · 🟡 in progress · ⬜ not started · 🔒 blocked

## Foundation (Layer 0–3)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| F0 | Monorepo scaffold (api / dif / infra / skills) | ✅ | 2026-06-16 |
| F0 | Build doctrine (CLAUDE.md) + progress tracker | ✅ | 2026-06-16 |
| F0 | Project skills (6) authored | ✅ | 2026-06-16 |
| L0 | Rust core types: `IntentVec`, `Paise`, `ResponseShape` | ✅ | scaffold compiles + tests |
| L0 | Python money/intent mirror (`core.money`, `core.intent`) | ✅ | exact paise arithmetic |
| L1 | Mahsa: global 8-dim fold | ✅ | `/fold` live, deterministic |
| L1 | Mahsa: hierarchical validator + `rules.yaml` loader | ✅ | seed rules wired |
| L1 | Mahsa: unfold → ResponseShape | ✅ | layout/flags/banners |
| L1 | Mahsa: critic (prior update) | ⬜ | stub present |
| L1 | Mahsa: property tests (proptest) | ✅ | fold invariants |
| L1 | Mahsa: HTTP integration tests | ✅ | `/health`, `/fold` |
| L2 | `schema.sql` — all 40+ tables, indexes, constraints | ✅ | all 12 domains + shared `documents` done |
| L2 | SQLAlchemy models + session | ✅ | all 12 domains modelled |
| L2 | Alembic migrations | ⬜ | |
| L3 | `MahsaClient` (httpx → Rust sidecar) | ✅ | unit + integration tested |
| L3 | `DomainRouter` (keyword classifier) | ✅ | treasury routed; others registered |
| L3 | Hash-chained `AuditLog` | ✅ | append-only, tamper-evident, tested |
| L3 | FastAPI app skeleton + `/health` + base HTMX template | ✅ | runs locally |

## Domain Modules (Layer 4) — 12 modules

| ID | Module | Rust fold+rules | Python service | Router/UI | Tests | Status |
|----|--------|-----------------|----------------|-----------|-------|--------|
| D01 | treasury  | ✅ | ✅ (CSV→cash/burn/runway) | 🟡 | ✅ | 🟡 reference slice |
| D02 | revenue   | ✅ | ✅ (invoicing/AR aging/dunning/credit notes/GSTR-1 bridge) | 🟡 | ✅ | 🟡 core complete; revenue-recognition/IRN/export/email pending |
| D03 | payables  | ✅ | ✅ (TDS 194C/J/H/I, 3-way match, AP aging, MSME, ITC bridge) | 🟡 | ✅ | 🟡 core complete; recurring/early-pay/payment-run pending |
| D04 | payroll   | ✅ | ✅ (PF/ESI/PT/TDS/gratuity/bonus, payroll run) | 🟡 | ✅ | 🟡 core complete; ECR/payslip/Form16/LWF/leave pending |
| D05 | gst       | ✅ | ✅ (GSTIN/ITC set-off/GSTR-3B/GSTR-1/recon) | 🟡 | ✅ | 🟡 core complete; e-invoice/RCM/GSTR-9/HSN master/LUT pending |
| D06 | tax       | ✅ | ✅ (advance tax 234C, TDS returns 234E, TDS aggregation, 44AB, MAT) | 🟡 | ✅ | 🟡 core complete; 234B/26AS/ITR/80-IAC/TP pending |
| D07 | ledger    | ✅ (LEDGER-001; no sub-vector) | ✅ (COA, double-entry, TB, P&L, BS, depreciation) | 🟡 | ✅ | 🟡 core complete; GL view/cash-flow/bank-recon/auto-posting pending |
| D08 | forecast  | ✅ (FORECAST-001; no sub-vector) | ✅ (budget variance, cash projection, scenarios, burn multiple, unit economics) | 🟡 | ✅ | 🟡 core complete; headcount/re-forecast/rev-recognition pending |
| D09 | equity    | ✅ | ✅ (cap table, ESOP pool, SAFE conversion, dilution, snapshots) | 🟡 | ✅ | 🟡 core complete; convertibles/investor-reporting/dividend/certs/buyback pending |
| D10 | compliance| ✅ | ✅ (statutory calendar, seed, T-7/T-1/T-0 alerts, filing-status) | 🟡 | ✅ | 🟡 core complete; MCA filings/secretarial/audit-pack/DPIIT pending |
| D11 | expense   | ✅ (EXPENSE-001; no sub-vector) | ✅ (claim workflow, policy check, petty cash, analytics, receipt parse) | 🟡 | ✅ | 🟡 core complete; OCR image pipeline/card-recon/mileage pending |
| D12 | vault     | ✅ (VAULT-001; no sub-vector) | ✅ (ingest+hash, dedup, classify, retention, search, integrity) | 🟡 | ✅ | 🟡 core complete; OCR image pipeline/auto-archive/RBAC pending |

## Email & UI (Layer 5)

| ID | Item | Status |
|----|------|--------|
| U1 | Design tokens + base layout (pixel polish baseline) | ✅ |
| U2 | Dashboard — KPI strip, domain health cards, compliance calendar, approvals queue | ✅ (cron-refresh later) |
| U3 | Daily 8pm CFO brief email (compose + render + channel; cron scheduling pending) | ✅ |
| U4 | Compliance alert / payroll approval / investor update emails | ✅ (compose+render+send) |
| U5 | CFO health collector + brief composer (`core/cfo.py`) | ✅ |
| U6 | Email channel (Jinja2 renderer + pluggable transport: InMemory/SMTP) | ✅ |

## Integration (Layer 6)

| ID | Item | Status |
|----|------|--------|
| I1 | End-to-end loop test (query→Maisha→Mahsa→render→audit) | ✅ per-domain loops + all-12 CFO brief green |
| I2 | 1-month parallel run | ⬜ |
| I3 | Backup/restore (restic) + runbook | ⬜ |

## Decisions / deviations from PRD

- 2026-06-16: LLM fallback row updated to `claude-opus-4-8` / `claude-sonnet-4-6` (PRD said Sonnet 4.5 / GPT-5-mini, now stale).
- 2026-06-16: Money represented as integer **paise** internally (PRD `REAL` columns kept at the DB edge; conversion at the service boundary) — required for zero-error exact arithmetic.
- 2026-06-16: Poetry not available on host; using PEP-621 `pyproject.toml` (pip/venv friendly, Poetry-compatible).
- 2026-06-16: **Payroll (D04) core built.** Statutory calculators are **FY 2025-26, new tax
  regime** (std deduction ₹75k, s.87A rebate at ₹12L taxable + marginal relief, 4% cess);
  PF on Basic capped at ₹15k @12%, ESI @0.75/3.25% with ₹21k ceiling (round-up), PT modelled
  for **MH + KA only** (others return ₹0 — explicit, see manifest), gratuity 15/26, bonus
  8.33% capped at ₹7k. Two new Mahsa rules: PAYROLL-003 (negative net pay → block),
  PAYROLL-004 (bonus under-provision → warning). Re-verify statutory values each Finance Act.
- 2026-06-16: Mahsa rule set now 14 rules (was 12). Rust: 30 tests; Python: 49 tests.
- 2026-06-16: **GST (D05) core built.** GSTIN validation (format + GSTN check digit), statutory
  ITC set-off (Rule 88A: IGST→IGST/CGST/SGST, then CGST→CGST/IGST, SGST→SGST/IGST; CGST/SGST
  never cross), GSTR-3B cash liability + late fee (₹50/day, ₹20 nil, capped) + s.50 interest
  (18% p.a.), GSTR-1 B2B/B2C/HSN summary with HSN/GSTIN validation, GSTR-2B ITC reconciliation
  (Rule 36(4) ratio). New rule GST-003 (GSTR-1↔3B mismatch → warning). Outward supplies are
  computed from passed-in lines until the revenue module lands. Rule set 15; Rust 33 tests,
  Python 63 tests.
- 2026-06-16: **Revenue (D02) core built.** GST-compliant invoicing (intra CGST+SGST vs inter
  IGST by supplier-vs-customer state), TDS on taxable value, AR aging (0-30/31-60/61-90/90+),
  dunning schedule (T-7/T-3/T-1/T+1/T+7), credit-note timeliness (CGST s.34 — 30 Nov following
  FY); calcs in `domains/revenue/revenue_calc.py`. New rule REVENUE-002 (customer concentration
  >40% → warning). **GST interim gap CLOSED**: `RevenueService.gstr1_lines()` feeds
  `GstService.build_gstr1()` (cross-module test). Pending: revenue recognition/deferred,
  IRN+QR, export/LUT, dunning email dispatch. Rule set 16; Rust 36 tests, Python 76 tests.
- 2026-06-16: **Payables (D03) core built.** Vendor master, TDS engine (194C 1%/2%, 194J 10%/
  2%, 194H 2%, 194I 2%/10% — rates+single+aggregate thresholds, FY25-26), PO↔GRN↔invoice
  3-way match (±5%), AP aging, MSME 45-day clock (s.43B(h)); calcs in
  `domains/payables/payables_calc.py`. New rule PAYABLES-002 (3-way variance >5% → warning).
  **GST input-side bridge**: `PayablesService.input_tax_credit()` feeds `GstService.file_gstr3b`
  ITC set-off (cross-module test). Pending: recurring payables, early-pay discount, payment
  run. Rule set 17; Rust 39 tests, Python 90 tests. **5/12 domains built.**
- 2026-06-16: **Tax (D06) core built.** Advance-tax schedule + s.234C deferment interest (with
  12%/36% relief provisos), s.234E TDS-return late fee (₹200/day capped at TDS), s.44AB audit
  trigger (₹1Cr/₹10Cr/₹50L), MAT s.115JB (15%+cess); calcs in `domains/tax/tax_calc.py`. New
  rule TAX-003 (TDS return late → warning). **TDS aggregation bridge**:
  `TaxService.tds_deducted_summary()` pulls TDS from payroll (s.192) + payables (194x) — the
  third cross-module bridge. Pending: s.234B, 26AS recon, ITR prep, 80-IAC holiday, transfer
  pricing. Rule set 18; Rust 42 tests, Python 101 tests. **6/12 domains built.**
- 2026-06-16: **Ledger (D07) core built.** Double-entry posting (balanced-or-reject), chart of
  accounts, trial balance, P&L, balance sheet (accounting-equation check), depreciation
  (SLM/WDV Schedule II); calcs in `domains/ledger/ledger_calc.py`. Ledger has **no Mahsa
  sub-vector** (not one of the 8 health domains) — instead rule LEDGER-001 enforces the trial
  balance tying out (metric `trial_balance_diff_paise`, op `ne` 0 → block), proving
  domain-scoped rules work without a fold. Pending: GL view, cash-flow statement, bank recon,
  auto journal posting from other modules. Rule set 19; Rust 43 tests, Python 112 tests.
  **7/12 domains built.**
- 2026-06-16: **Compliance (D10) core built.** The statutory calendar (uses the existing
  shared `compliance_calendar` table — no new model): seed standard monthly deadlines
  (TDS 7th/PF 15th/ESI 15th/GST 20th/PT 21st of following month), T-7/T-1/T-0 + overdue
  alerts, per-statute filing-status health feeding the 8-dim compliance sub-vector; logic in
  `domains/compliance/compliance_calc.py`. Drives the existing global COMPLIANCE-002 rule
  (overdue_filings>0 → warning). Pending: MCA filings (AOC-4/MGT-7/DIR-3/DPT-3), secretarial,
  audit-support package, DPIIT. Rust 46 tests, Python 119 tests. **8/12 domains built.**
- 2026-06-16: **Equity (D09) core built.** Cap table (ownership % by category), ESOP pool %
  with board-approval gate (EQUITY-001 — pool >10% without approval → block), SAFE conversion
  (valuation cap vs discount, better-for-investor wins), round dilution, cap-table snapshots
  (incl. `esop_board_approved` flag added to the model); calcs in `domains/equity/equity_calc.py`.
  8-dim equity sub-vector. Pending: convertible notes, investor-reporting generator, dividends
  (s.123), share certificates, rights/buyback. Rust 49 tests, Python 129 tests. **9/12 built.**
- 2026-06-16: **Forecast (D08) core built.** Budget variance, rolling cash projection with
  overdraft detection, scenario engine (revenue mult / extra hires), burn multiple, unit
  economics (CAC/LTV/payback); calcs in `domains/forecast/forecast_calc.py`. **No sub-vector**
  (like ledger) — rule FORECAST-001 (projected cash < 0 within horizon → warning). Pending:
  headcount→payroll forecast, quarterly re-forecast, revenue-recognition timing. Rule set 21;
  Rust 50 tests, Python 139 tests. **10/12 domains built — only expense + vault remain.**
- 2026-06-16: **Expense (D11) core built.** Claim → approval → reimbursement workflow,
  per-category policy check (EXPENSE-001), petty-cash ₹10k threshold, category analytics, and a
  testable **receipt parser** (extracts amount/GSTIN/date from OCR text; Tesseract image→text
  is the stubbed boundary); calcs in `domains/expense/expense_calc.py`. **No sub-vector** → rule
  EXPENSE-001 (over-policy claims → warning). `receipt_document_id` is a plain column for now
  (FK to vault `documents` added when vault lands). Pending: OCR image pipeline, card recon,
  mileage/per-diem. Rule set 22; Rust 51 tests, Python 148 tests. **11/12 domains — only vault remains.**
- 2026-06-16: **Vault (D12) core built — ALL 12 DOMAINS NOW COMPLETE.** Document ingestion with
  SHA-256 content hashing (id = content hash → duplicate detection), classification, statutory
  retention (7y/3y/permanent), full-text search, integrity verification; calcs in
  `domains/vault/vault_calc.py`. Vault owns the shared `documents` table; expense's
  `receipt_document_id` FK to it was restored. **No sub-vector** → rule VAULT-001 (SHA-256
  integrity failure → block). Pending: OCR image pipeline, auto-archive, RBAC. Rule set 23;
  Rust 52 tests, Python 158 tests. **12/12 domains core-complete; `_PENDING` registry removed.**
- 2026-06-16: **Layer 5 (CFO brief + email channel) started.** `core/cfo.py`: `collect_health`
  folds all 12 domains through Mahsa into a scorecard; `compose_brief` (pure) builds the daily
  8pm Domain Health Dashboard (worst-first, needs-attention, approvals, overall score).
  `core/email/`: Jinja2 `daily_brief.html` (inline-styled, client-safe), pluggable transport
  (`InMemoryTransport` for tests, `SmtpTransport`→MailHog), `EmailChannel.send_daily_brief`.
  Web `/` dashboard now shows **live per-domain health scores/status** from Mahsa, degrading
  gracefully if the sidecar is down. New `/cfo/brief`, `/cfo/brief.html`, `/cfo/brief/send`.
  Engine fix: in-memory SQLite now uses StaticPool (shared connection). Rust 52, Python 165.
  Pending Layer 5: KPI strip/calendar/approvals on the web dashboard, U4 email templates,
  cron scheduling of the 8pm brief (ARQ/cron).
- 2026-06-16: **Layer 5 dashboard + U4 emails done.** `core/overview.py` (`collect_kpis`,
  `upcoming_deadlines`) feeds the web `/` KPI strip (cash/burn/runway/AR/AP), compliance
  calendar, and approvals queue (all DB reads → render without Mahsa). U4 emails: pure
  composers in `core/email/compose.py` + inline-styled templates (compliance_alert /
  payroll_approval / investor_update) + a `rupees` Jinja filter + `EmailChannel` methods.
  Remaining Layer 5: cron-schedule the 8pm brief + alert dispatch (ARQ/cron, infra). Rust 52,
  Python 169.
- 2026-06-23: **Harness layer P0-① — golden eval harness built (LLM-layer foundation).** New
  strategy/plan docs (`HARNESS_ENGINEERING.md`, `P0_HARNESS_PLAN.md`) map published
  harness-engineering work (Anthropic *Building Effective Agents*, OpenAI Structured
  Outputs/Agents-SDK, SWE-agent ACI, ReAct/Reflexion, τ-bench/Inspect pass^k, DSPy, MCP) onto
  the project; new `skills/harness-layer`. Code: `app/llm/schema.py` — the strict `ActionClaim`
  contract (extra=forbid, money as paise `StrictStr`, never floats; `canonical()` for pass^k).
  `api/evals/` — declarative `EvalCase`/`Expectation`, `ScriptedProducer` (no-LLM stub),
  scorers (`paise_exact`, `citation_correct`, `abstains_when_thin`), pass^k runner + CLI,
  text/JSON report. Cases for **treasury** (runway-healthy + no-data-abstain) and **gst**
  (3b-late → GST-001 citation), ground truth cross-checked against the real `build_snapshot`.
  New `make eval` gate, wired into `make verify`; `evals` added to the editable install +
  `mypy app evals`. **`make verify` green: Rust 52, Python 176 (+7 harness tests incl. a
  negative case per scorer), eval 3/3.** The LLM is still a drafter only — Mahsa unchanged,
  Golden Rule intact. Next: P0-①b (cases for the other 10 domains) → P0-② (real LLM generator).
- 2026-06-24: **Harness layer P0-①b — eval cases for all 12 domains.** Added `api/evals/cases/`
  for revenue (missing-IRN turnover), payables (MSME-overdue → PAYABLES-001 citation), payroll
  (min net pay), tax (TDS 40-days overdue), ledger (balanced books / net profit), forecast
  (no-projection baseline), equity (ESOP pool %), compliance (overdue filing → COMPLIANCE-002),
  expense (over-policy → EXPENSE-001), vault (integrity clean) — plus the existing treasury + gst.
  Every case's ground truth cross-checked against the real `build_snapshot` (values mirror the
  validated `tests/unit/<domain>/test_*_service.py` snapshot assertions, as_of 2026-06-16).
  **`make verify` green: Rust 52, Python 176, eval 13/13 across 12 domains.** Citation scorer now
  exercised on 3 domains (gst/payables/expense/compliance). Next: P0-② real LLM generator.
- 2026-06-24: **Harness layer P0-② — the Maisha LLM generator (drafting layer).** New
  `api/app/llm/`: `client.py` (LLMClient protocol; `OllamaClient` via `/api/chat` with
  `format`=JSON-schema constrained decoding + temp 0; `ClaudeClient` forced-tool fallback;
  `CannedClient`; `build_client`), `tools.py` (deterministic calc-wrapping tools + `flatten`/
  `enrich` so the model never does arithmetic — runway/late-fee derived by tools), `prompt.py`
  (pure system+user assembly; "do NOT do arithmetic", FACTS-only numbers, RULES-only citations,
  abstain-when-thin; per-domain rule hints), `maisha.py` (`MaishaGenerator.produce` →
  enrich→prompt→constrained LLM→parse `ActionClaim`, pins router's domain; `ClaimProducer`
  protocol shared by run_loop + eval harness). Config: `MAISHA_LLM_PROVIDER` (default "off"),
  ollama/claude settings, temp 0. `run_loop` gains an optional `generator` step BEFORE the
  Mahsa fold (claim attached to `LoopOutcome`, never trusted — Mahsa still folds the snapshot;
  default None = unchanged). Eval harness `--provider stub|ollama|claude` + `make eval-real`;
  clients unit-tested via `httpx.MockTransport` (no live server). **`make verify` green: Rust
  52, Python 196 (+20), eval 13/13.** Golden Rule intact. NOTE: persisting LLM trace fields
  (model/prompt/claim hashes) to the audit log is P1 (needs a schema column/table). Next:
  P0-③ evaluator-optimizer retry loop (regenerate on Mahsa RED, bounded, template fallback).
- 2026-06-24: **Harness layer P0-③ — evaluator-optimizer retry loop. P0 COMPLETE.** New
  `api/app/llm/retry.py`: the evaluator is the deterministic fact set — `unbacked_numbers`
  flags any claimed value not present among `enrich(snapshot)` facts (the Golden Rule applied
  live to the draft); `generate_verified` regenerates with feedback (the unbacked values +
  Mahsa's triggered rules) bounded by `MAISHA_LLM_MAX_RETRIES` (default 2); on exhaustion
  `fallback_claim` returns a fully fact-backed claim and flags `requires_approval`. `feedback`
  threaded through `MaishaGenerator.produce`/`ClaimProducer`/prompt. `run_loop` now folds via
  Mahsa first (verdict is independent of the draft), then runs `generate_verified`; LoopOutcome
  gains `claim_verified` + `requires_approval` (Mahsa RED OR retry exhaustion). **`make verify`
  green: Rust 52, Python 203 (+7), eval 13/13.** No unbacked number can reach a human.
  **All P0 done (①eval harness, ①b 12-domain cases, ②LLM generator, ③retry loop).** Next is
  P1: input guardrails (injection/PII), persist LLM trace fields to audit_log (schema change),
  determinism hygiene; then P2 (DSPy prompt compilation, MCP tool servers, eval-gated routing).
- 2026-06-24: **Harness layer P1 — input guardrails + LLM tracing + determinism hygiene.**
  (a) `app/llm/guardrails.py`: prompt-injection/jailbreak detection (blocks → safe abstain,
  model never called) + PII redaction (PAN/Aadhaar/GSTIN/email/phone, applied only for cloud
  provider); wired into `MaishaGenerator.produce` (new `redact_pii`/`label` ctor args).
  (b) `app/db/models/shared.py::LlmTrace` + `app/core/trace_store.py`: per-draft observability
  row (model_label, input_sha256 = hash of domain+query+snapshot, claim_sha256, attempts,
  verified, requires_approval, linked to audit_log.this_hash) — hashes only, no raw prompt;
  written in `run_loop` when a claim is produced. (c) Determinism: temp 0 (config), model id in
  `model_label`, input/claim hashes give reproducibility; graceful degradation (LLM off → no
  claim) intact. `_build_producer` sets label `provider:model` + cloud PII flag. **`make verify`
  green: Rust 52, Python 215 (+12: guardrails, generator-guard, trace), eval 13/13.** Deferred:
  token-count capture in trace (needs usage plumbing from clients); persisting guard findings
  (currently logged). Next: P2 (DSPy-style prompt compilation, MCP tool servers, eval-gated
  Ollama→Claude routing).
- 2026-06-24: **Harness layer P2 (testable slice) — eval-gated model routing + latency trace.**
  `app/llm/routing.py`: `decide_routes` (pure) maps each domain to the local model only where it
  scored perfectly on the golden eval (threshold default 1.0 — zero-error bar), else the cloud
  fallback; `RoutedGenerator` (a ClaimProducer) dispatches each draft to the chosen provider.
  `LlmTrace.latency_ms` + `time.perf_counter` capture around the draft step in run_loop.
  **`make verify` green: Rust 52, Python 219 (+4), eval 13/13.** DSPy-style prompt compilation
  (P2-7) and MCP tool servers (P2-8) are scaffolding-deferred — they need a live Ollama/Claude
  (DSPy optimizes against measured eval scores) or the `mcp` dep; tools already centralized in
  `llm/tools.py` for a clean lift. See HARNESS_ENGINEERING.md §3a for the status matrix.
- 2026-06-24: **Frontend F1+F2 — navigation + domain workspaces + Ask Maisha (spine).** Wrote
  FRONTEND_PRD.md (PM spec: thesis "make trust visible", IA, hero wireframes, F1–F7 roadmap).
  F1: real `/d/{domain}` pages (reusable `domain.html`) showing deterministic facts + Mahsa
  health/score + triggered-rule citations; fixed the dead sidebar (now links to real pages);
  `app/web/format.py` (money/humanize formatting). F2: **Ask Maisha** — `app/core/ask.py`
  orchestrator (classify → snapshot → enrich facts → optional Mahsa fold → optional LLM draft →
  one `Answer` view-model), `/ask` page + `POST /ask` HTMX partial + appbar command bar (`/`
  or ⌘K to focus); `answer_card.html` renders the harness pipeline (figures with ✓ verified
  marks, citation chips, Mahsa verdict, provenance). Degrades cleanly: no LLM → deterministic
  figures; Mahsa offline → no verdict; an unbacked number is flagged ⚠, never shown as fact.
  CSS on existing tokens, HTMX-driven, no build step. **`make verify` green: Rust 52, Python
  227 (+8: ask orchestrator unit + app route tests), eval 13/13.** Remaining: F3 action
  forms · F4 approvals flow · F5 CFO panel · F6 audit/trace viewer · F7 polish.
- 2026-06-24: **Frontend F3 — action bar + drawer forms (domains become operational).** New
  `app/web/actions.py`: a declarative action registry (Field/Action + handlers) — handlers call
  existing domain services directly (JSON `/api/*` routes untouched) and money is entered in
  rupees → exact paise at the edge. Wired actions for ledger (create account), compliance (add
  deadline), equity (add shareholder), expense (submit claim), vault (ingest) — the pattern;
  remaining domains are config repeats. Routes: `GET /d/{domain}/action/{key}/form` (drawer
  form) + `POST /d/{domain}/action/{key}` (run handler → commit → OOB-refresh #figures + toast;
  bad input re-renders the form with an error). Templates: `partials/{figures,drawer_form,
  action_success}.html`; domain page gains the action bar + drawer + global toast. HTMX-driven,
  no build step. **`make verify` green: Rust 52, Python 235 (+8: action handlers unit + route
  tests incl. validation error), eval 13/13.** Remaining: F4 approvals · F5 CFO · F6 audit/trace
  · F7 polish.
- 2026-06-24: **Frontend F4 — approvals review → audit-chain write.** New `app/core/approvals.py`
  (`pending_approvals` lists Mahsa-flagged domains w/ citations + a snapshot `state_hash` +
  resolution; `record_decision` re-folds, seals an `approval.{approved,rejected}` entry onto the
  hash-chained audit log via audit_store, and persists a `Decision`), `app/core/decision_store.py`,
  `Decision` model. Routes `/approvals` (queue) + `POST /approvals/{domain}/decide` (HTMX → refresh
  list + toast; degrades honestly if Mahsa offline). A decision resolves an item until the books
  (snapshot hash) change, then it resurfaces. Nav + dashboard link to /approvals. **`make verify`
  green: Rust 52, Python 241, eval 13/13** (incl. audit-chain still verifies after a decision).
  Remaining: F5 CFO panel · F6 audit/trace viewer · F7 polish.
- 2026-06-24: **Frontend F5 — CFO Strategy panel.** `app/core/strategy.py` (deterministic, no
  Mahsa/LLM): `run_scenario` (revenue multiplier + extra cost → monthly net change / min cash /
  runway via forecast_calc), `cap_table`, `investor_update` (compose_investor_update from KPIs +
  cap table). `/cfo` page: KPI strip + scenario engine (HTMX form → result) + cap-table bars +
  investor-update preview w/ Send (EmailChannel→SMTP, guarded → toast) + upcoming compliance.
  Nav link added. **`make verify` green: Rust 52, Python 249, eval 13/13.** Remaining: F6
  audit/trace viewer · F7 polish.
- 2026-06-24: **Frontend F6 — audit & trace viewer.** `/audit` page renders the hash-chained
  audit log (newest-first) with an in-browser chain-integrity check (`verify_chain`) shown as a
  CHAIN INTACT/BROKEN badge, plus the LLM trace table (model, attempts, verified, requires-
  approval, latency, claim hash) via new `trace_store.recent`. Reads only; renders without
  Mahsa/LLM. Nav link added. **`make verify` green: Rust 52, Python 252, eval 13/13.** This
  surfaces the trust story the harness writes to. Remaining frontend: F7 polish (charts,
  skeletons, a11y, mobile).
- 2026-06-24: **Frontend F7 — Metallic Black polish + full screen/flow audit. FRONTEND DONE.**
  Redesigned `tokens.css` into a premium metallic-dark theme: brushed-metal gradients
  (`--metal-bg/surface/rail/accent`), bevelled edges, an SVG fractal-noise grain texture, dark
  status palette. `app.css` F7 block: metallic surfaces on nav/cards/appbar/buttons/tables,
  gradient brand wordmark + KPI values, card hover-lift, accent-rail answer card, domain health
  **score bars**, accessible `:focus-visible` rings, `aria-current` nav, prefers-reduced-motion,
  HTMX loading states + shimmer skeleton, and a **responsive** layout (rail collapses to a top
  strip < 880px; tables scroll). Dashboard domain cards are now links to `/d/<domain>`.
  **Final coverage sweep**: parametrized tests render all 12 domain pages + all 5 top-level
  screens. **`make verify` green: Rust 52, Python 269, eval 13/13.** All of F1–F7 complete —
  the frontend is feature-complete and polished.
- 2026-06-24: **Trends — snapshot history + honest sparkline charts.** `MetricSnapshot` table +
  `app/core/history_store.py` (`capture` writes one row per numeric fact per domain at a point in
  time; `domain_series` reads them chronologically — observability floats, never money math).
  `app/web/charts.py::sparkline` = pure dependency-free inline SVG (≥2 real points or empty —
  no fabricated trends; green/red by direction). Domain pages render a Trends section per metric
  with history; `POST /history/capture` (button on CFO page; cron-ready) records a capture.
  **`make verify` green: Rust 52, Python 274, eval 13/13.** Real charts unlocked without
  inventing data; richer chart types can layer on the same series later.
- 2026-06-24: **Layer 6 — scheduled jobs (snapshot capture + 8pm CFO brief) wired to cron.**
  `app/scheduler.py` (pure `next_run`/`seconds_until_next`, tz-aware via zoneinfo+tzdata, clock
  injected) + `app/jobs.py`: `run_capture` (history_store.capture), `run_brief` (collect_health →
  compose_brief → EmailChannel.send_daily_brief), `run_once` (self-creates schema; catches
  errors so a tick never crashes), `serve` (sleep-until-next loop). CLI `python -m app.jobs
  capture|brief|all|serve` — cron-friendly AND a long-lived service. Config `MAISHA_BRIEF_HOUR/
  MINUTE/TZ` (default 20:00 Asia/Kolkata). Added a `scheduler` service to docker-compose (runs
  `serve`) + Makefile `capture`/`brief`/`scheduler` targets. `tzdata` added to deps. **`make
  verify` green: Rust 52, Python 279, eval 13/13** (scheduler math + capture/brief jobs tested;
  CLI capture verified standalone = 90 metrics). Daily 8pm brief + trend capture now automated.
- 2026-06-24: **Layer 6 — 1-month parallel run STARTED.** `ParallelRun`/`ParallelObservation`
  models + `app/core/parallel.py`: start_run (30-day window), record_observation (founder's
  existing-system figure), reconcile (external vs Maisha's captured MetricSnapshot for that
  (domain,metric)/date → variance + within-tolerance), readiness (deterministic GO/HOLD —
  GO only when every comparison agrees across the full window). `/parallel` page (start CTA →
  reconciliation table + readiness banner + observe form), nav link, `docs/PARALLEL_RUN.md`
  runbook. **`make verify` green: Rust 52, Python 285, eval 13/13.** **Run #1 kicked off in the
  data DB: active 2026-06-24 → 2026-07-24, day-1 capture = 90 metrics; readiness HOLD until daily
  observations accrue.** Daily ritual: scheduler captures Maisha nightly; founder records their
  figures; cut over on GO.
- 2026-06-24: **Deferred per-domain features — batch 1 (6 features, pure-calc, exact paise).**
  tax `interest_234b` (s.234B 1%/mo on shortfall, ₹100 round-down), payables `early_payment_discount`
  (2/10-net-30 capture), forecast `headcount_forecast` (headcount→payroll cost), equity
  `convertible_note_value` (simple + monthly-compound accrual), ledger `general_ledger` (account-wise
  running balance), treasury `burn_attribution` (debits by category over a window). Each unit-tested;
  6 manifest rows flipped ⬜→✅. No new Mahsa rules needed (computations/reports, not validations).
  **`make verify` green: Rust 52, Python 298, eval 13/13.** Remaining deferred features (~44) are
  mostly external-dep/integration (OCR images, PDF payslip/Form-16, ECR, MCA forms, ITR) or larger
  workflows — next batches can take the calc-shaped ones (e.g. ledger cash_flow/bank_recon, gst rcm,
  tax 234B done, equity convertible done).
- 2026-06-24: **Deferred per-domain features — batch 2 (6 more, calc-shaped, exact paise).**
  ledger `cash_flow` (direct method, classify by counterpart account type; `create_account` gained
  `is_cash`/`is_bank` flags) + `bank_reconciliation` (book vs statement ± in-transit/unpresented),
  gst `rcm_liability` (reverse charge tax + ITC), tax `reconcile_26as` (Form 26AS vs books by TAN),
  compliance `mca_deadlines` (AOC-4/MGT-7/DPT-3/DIR-3 KYC from AGM date), equity
  `dividend_distribution` (s.123 out-of-profits check + per-share). Each unit-tested; 6 manifests
  flipped ⬜→✅. **`make verify` green: Rust 52, Python 309, eval 13/13.** 12 deferred features now
  done across 2 batches; remaining are external-dep (OCR/PDF/ECR/ITR) or larger workflows.
- 2026-06-24: **Deferred per-domain features — batch 3 (5 more, calc-shaped).** revenue
  `deferred_revenue_schedule` (straight-line recognition, final period absorbs rounding), forecast
  `rolling_reforecast` (actuals + remaining budget), tax `tax_holiday_deduction` (s.80-IAC 3-of-10),
  gst `hsn_rate` (HSN master lookup + well-formedness), treasury `sweep_suggestion`/`treasury_policy`
  (idle cash beyond a runway buffer → FD ladder). Each unit-tested; 5 manifests flipped ⬜→✅.
  **`make verify` green: Rust 52, Python 322, eval 13/13.** 17 deferred features done across 3
  batches; remaining are external-dep (OCR/PDF/ECR/ITR) or larger cross-module workflows.
- 2026-06-24: **Deferred feature — ledger auto_posting (cross-module workflow).** `ledger_calc`
  balanced-entry builders for source events: `payroll_journal` (Dr salary / Cr bank+statutory,
  enforces net+statutory=gross), `sales_journal` (Dr AR / Cr sales+GST-output), `gst_payment_journal`
  (Dr GST payable / Cr bank). `LedgerService.auto_post` posts them tagged with a non-manual
  `source` (sets is_auto_generated), reusing the balance-guarded post_journal_entry; rejects
  source="manual". Lets payroll/GST/revenue auto-generate audit-tagged journal entries that keep
  the trial balance tied. Unit-tested; manifest flipped ⬜→✅. **`make verify` green: Rust 52,
  Python 327, eval 13/13.** 18 deferred features done.
- 2026-06-24: **Deferred feature — gst GSTR-9 annual return.** `gst_calc.gstr9_annual` consolidates
  a year from existing monthly artefacts: per-period `build_gstr1(...)['totals']` (outward) +
  GSTR-3B records `{output, itc, tax_paid_cash}` → annual outward (taxable+tax by head), output
  tax, ITC availed, cash paid, and the **GSTR-1-vs-3B differential** (>0 = under-declared in 3B /
  additional liability) with a reconciled flag. Pure, exact paise; unit-tested; manifest flipped
  ⬜→✅. **`make verify` green: Rust 52, Python 329, eval 13/13.** 19 deferred features done.
- 2026-06-24: **Deferred feature — revenue dunning_send (automated reminders).** `RevenueService.
  pending_dunning` (open invoices whose T-7/T-3/T-1/T+1/T+7 schedule fires today, with customer +
  outstanding) + async `dunning_run` (dispatches via EmailChannel, skips invoices with no email).
  New `compose_dunning` (tone per stage), `dunning_reminder.html` email template, `EmailChannel.
  send_dunning`. Wired into the scheduler: `app.jobs` gains a `dunning` command and runs it in the
  daily `all`/`serve` pass; `make dunning` for one-off. Tested via InMemoryTransport (dispatch +
  skip-no-email + schedule firing). Manifest flipped ⬜→✅. **`make verify` green: Rust 52, Python
  332, eval 13/13.** 20 deferred features done; reuses the existing dunning schedule + email channel.
