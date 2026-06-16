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
