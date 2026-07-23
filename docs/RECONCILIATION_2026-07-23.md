# QG.4 RECONCILIATION — 2026-07-23

Weekly reconciliation per MMX-1.0 §14 QG.4: PROGRESS vs spec, §15 checklist, badge-honesty
spot audit, cut-list review. Prepared by ORCH-delegated auditor. Read-only on code; the only
writes of this pass are this document, one PROGRESS.md entry, and PROGRESS_BOARD.md corrections.

**This is the pre-pilot honesty document.** Nothing below is softened.

---

## 0 · Summary

| Bucket | Count (of 77 spec tickets, §3–§14) |
|---|---|
| DONE (evidence spot-checked) | 52 |
| PARTIAL | 11 |
| OPEN (not started / blocked) | 9 |
| HUMAN-only | 4 (WS6.4, WS9.4, WS10.3, WS7.V) |
| Cancelled by owner (spec deviation) | 1 (WS7.10 i18n/Hinglish) |

- **Badge-honesty audit: 25 rendered figures + 2 tamper probes, 0 dishonest badges.**
  Every ✓ traced to a live Mahsa recompute matched to the paisa; every ◐ states why;
  no raw unbadged number on any money surface; demo-org audit chain verifies intact.
- **CRITICAL findings: none** (no dishonest badge, no untouchable cut).
- **HIGH governance finding (F1):** the launch checklist and the P0 gate require
  **CA-initialled** oracle vectors ("CA sign-off rows present in vectors", "300+ CA-initialled").
  Current truth: **171 vectors authored, 343 oracle tests green, 0 CA-initialled**
  (8 owner-initialled interpretations, 163 PENDING). The 2026-07-22 owner decision
  "no external CA" cannot amend the immutable spec (§0.1) — either a retained CA initials the
  vectors before GA, or the owner issues **MMX-1.1** amending §15 item 1 and the P0 gate.
  Until one of those happens, §15 item 1 is honestly **unmeetable**, not merely unfinished.
- **MEDIUM finding (F2):** WS7.10 Hinglish is in §15 item 6 but was cancelled by owner
  (English-only, 2026-07-23). Same remedy: MMX-1.1, or the item stays permanently red.
- **MEDIUM finding (F3):** a latent coverage-driven ✓ path exists (see §4.4) — unreachable
  today (verified empirically), but one un-guarded naming collision away from a §0.4 breach.
- §15 launch checklist: **2 items done, 2 code-done-human-pending, 6 partial, 1 open** (§3).

---

## 1 · Spec reconciliation §3–§14, ticket by ticket

Status legend: DONE / PARTIAL / OPEN / BLOCKED-CA / HUMAN. "Ev:" = PROGRESS.md entry (by tag).
Spot-checked claims are marked ✦ and detailed in §2.

### §3 WS1 — Statutory correctness

| Ticket | Status | Evidence + honest remainder |
|---|---|---|
| WS1.A1 | DONE | Ev `[WS1.A1]`. ✦ `api/app/core/statutory_regime.py` boundary 2026-04-01, earlier-of rule, form map. Payment-code table ships EMPTY (BLOCKED-CA). |
| WS1.A2 | BLOCKED-CA | Ev `[WS1.A2]`. Needs 1961→2025 SECTION map. Labour-side citation sweep since done (WS1.B4); income-tax sweep still blocked. |
| WS1.A3 | BLOCKED-CA | Ev `[WS1.A3]`. No CA fixtures in `tests/statutory_oracle/fixtures/`. |
| WS1.B1 | DONE | Ev `[WS1.B1]`+`[WS1.B1-wiring]`. ✦ engine + PF/ESI/bonus routed through `statutory_wage_base`. Defects #5/#6/#7 later fixed (`[WS1.C-labour-codes]`). |
| WS1.B2 | DONE | Ev `[WS1.B2]`+`[WS1.C-labour-codes]` (5y floor, ₹20L ceiling). **Known gap, recorded:** s.53(2) part-year >6-months round-up NOT implemented — needs its own ticket before payroll GA. |
| WS1.B3 | DONE | Ev `[WS1.B3]`. Validator + rebalance, never mutates. |
| WS1.B4 | DONE | Ev `[WS1.B4+WS1.E3]`. ✦ Sweep + `check_no_stale_citations.sh` in `make gates`; watch items live. |
| WS1.C1–C5 | DONE | Ev `[WS1.C1..C5]` + `[WS1.C1-boundary]`. ✦ All 5 regression-locked; ✦ TDS at-threshold off-by-one fixed strict-`>` in BOTH engines; C5 migration debt paid in 0003 (`[WS4.2]`). |
| WS1.D1 | DONE | Ev `[WS1.D1]`. Unsourced params RAISE (TCS-goods, 206AA/AB floors BLOCKED-CA). |
| WS1.D2 | DONE | Ev `[WS1.D2]`. Due-date calendar days BLOCKED-CA (injected). |
| WS1.D3 | DONE | Ev `[WS1.D3]`. Composition rates mandatory params, raise if absent. |
| WS1.D4 | DONE | Ev `[WS1.D4]`+`[P2-2]`. Deemed-accept deadline BLOCKED-CA (date.max injection, stated in UI). |
| **WS1.D5** | **OPEN** | Board row was `[ ]` and is confirmed real: `[WS1.E2-expand]` defect D4 — `late_fee_3b` has **no AATO/turnover input**, so Notf 19/2021 caps (₹1k/₹2.5k CGST) are not modelled and the engine **overstates** late fees for smaller taxpayers beyond 40/100 days. Buildable by Claude (needs AATO entity attribute per spec). |
| **WS1.D6** | **OPEN** | `[WS1.E2-expand]` defect D5 — surcharge bands >₹50L not implemented in `annual_income_tax`. Spec says vectors from CA → BLOCKED-CA on values, engine work open. |
| WS1.D7 | DONE(core) | Ev `[WS1.D7]`. ₹50k inter-state + JSON artifact + honesty label done; **intra-state thresholds return pending** (WS2 packs carry them as blocked_ca) — board `[x]` slightly overstates, annotated. |
| WS1.D8 | DONE | Ev `[WS1.D8]`. |
| WS1.E1 | DONE | ✦ Re-run this audit: `pytest tests/statutory_oracle` → **343 passed** in 1.5s. |
| WS1.E2 | PARTIAL | ✦ Counted this audit: **171 vectors / 23 files; 0 CA-initialled, 8 owner-interpretation, 163 PENDING**. Gap to 300: 129. See finding F1. (Board said "all ca_initials PENDING" — 8 are owner-initialled interpretations; imprecise in the honest direction.) |
| WS1.E3 | DONE | Ev `[WS1.B4+WS1.E3]`. Manifest sha-verified packs, rollback proven 3 ways, SLA doc published. Ed25519 signing = documented OWNER-STEP, not claimed. |

### §4 WS2 — State packs

| Ticket | Status | Evidence + remainder |
|---|---|---|
| WS2.1 | DONE | Ev `[WS2.1+WS2.2]`. Framework w/ sourced/not_applicable/blocked_ca tri-state; silent-₹0 impossible (blocked compute RAISES). |
| WS2.2 | PARTIAL | PT sourced for MH/KA/TN(Chennai+VP)/TS/AP/GJ/WB, not_applicable DL/HR/UP proven. ✦ KA Feb ₹300 regression-locked. **Blocked:** TN-Madurai slabs (the owner's own base!), LWF/S&E/min-wage/stamp/e-way/LC-rules in every pack. No CA verification (F1). |
| WS2.3 | PARTIAL | Payroll PT + provenance endpoint wired. Remainder: LWF (legacy uncited table still feeds payslips — pack refuses, path not yet swapped), calendar/equity/e-way consumers, onboarding state selection, per-tenant pack-version display. |
| WS2.4 | OPEN | Expansion backlog untouched (legitimate breadth cut). |

### §5 WS3 — Mahsa recomputation (Prime Directive)

| Ticket | Status | Evidence |
|---|---|---|
| WS3.1 | DONE | ✦ `dif/src/recompute/` 7 modules; `mahsa_coverage.json` honest: 9 ported oracle targets, 5 declared unported (itr_computation, regime_for, form_name, retention_until, payroll_components). |
| WS3.2 | DONE | ✦ `dif/tests/parity.rs` + `tests/integration/test_parity_fuzz.py` (~5100 paise-granular cases) + live /fold MAHSA-PARITY block. Tamper probe re-proven live this audit (§4.3). |
| WS3.3 | DONE | Default-healthy dead; absence-behaviour tests. |
| WS3.4 | DONE | Verdict object; hash re-derived deterministically this audit (§4.2). |
| WS3.5 | DONE | Coverage json + tri-state badges; fail-closed to ◐/✕ verified in audit. |

### §6 WS4 — Multi-tenant platform

| Ticket | Status | Evidence + remainder |
|---|---|---|
| WS4.1 | DONE | SPEC-WS4 + RLS ENABLE+FORCE + `check_rls_coverage.sh` (46/46) + live redteam SQL. |
| WS4.2 | DONE(replay+importer) | Alembic 0002+ inline-RLS revisions; SQLite importer w/ checksum. **Supabase provisioning = Human.** |
| WS4.3 | DONE | Better Auth JWKS-verify only; legacy HMAC auth DELETED (`[P2-6]`). **OWNER-STEP:** frontend must set `maisha_jwt` cookie for HTMX surface; ✦ MFA enforcement is policy-complete but **only active when `MAISHA_MFA_CLAIM` is configured** (betterauth.py:81 "UNSET = MFA is not enforced") — owner config, not yet provably on. |
| WS4.4 | DONE(code) | Per-tenant chains + tamper tests + MCA doc. ✦ `compute_daily_root_for` exists; **external timestamping of the daily root = ops/Human, not wired** — §15 item 4 is not fully met until it runs somewhere. |
| WS4.5 | DONE | Tenant-iterated jobs, isolation + idempotency mutation-checked. |
| **WS4.6** | **OPEN** | api-nest promotion not started (api-nest tree exists, untracked; GST domain parity only). Owner architecture decision pending. Python remains main line — acceptable for pilot, open vs spec. |
| WS4.7 | PARTIAL | DB/RLS-layer negative matrix live in CI + memory red-team (16 probes) + full route×role RBAC matrix over real JWTs. Remainder: route-level **cross-org** attempts on every route + real object-storage paths (deferred to post-Supabase provisioning). |
| WS4.8 | DONE(core) | `scripts/ci_gate.sh` = single 19-step list, `make ci` + GH Actions run it verbatim; mahsa built first; KNOWN_STATUTORY_GAPS exact-set mechanism. **Canary "deliberately-broken PR fails each gate" never evidenced in PROGRESS** — worth one deliberate red PR. |

### §7 WS5 · §8 WS6

WS5.1/5.2/5.3 DONE (+`[WS5.1-wiring]`, ✦ API_ROUTE_GATES ~135 routes, full 6-role matrix, statutory filing hard-gate).
WS6.1/6.2/6.3 DONE (registry-derived 71/34/11, statutory grace, CA seat exemption mutation-checked).
**WS6.4 BLOCKED-HUMAN** (Razorpay account; billing E2E unbuilt until then).

### §9 WS7 — UI/UX

| Ticket | Status | Remainder |
|---|---|---|
| WS7.1 | DONE | Tokens + verification/money family split + lakh-crore lint (green). |
| WS7.2 | DONE | Chip + working panel + real per-figure verdict threading (`[fix:verdict-ask]`). |
| WS7.3 | DONE | Today view; penalties counter badge-backed or labelled estimate. |
| WS7.4 | PARTIAL | Five hubs + Altitude-2 keyboard entry forms shipped. **Per-role altitude default + remembered toggle: no evidence anywhere in PROGRESS** — board `[ ]` was right to stay open; now marked [~]. |
| WS7.5 | DONE | Exception Inbox w/ preview-then-confirm bulk. |
| WS7.6 | DONE(typed) | Preview→typed-confirm→sealed receipt on filings/payroll/approvals; E2E incl. tamper. Biometric confirm not built (typed only — acceptable reading of "typed/biometric"). |
| WS7.7 | DONE | Health strip + staleness downgrade, wiring-level mutation-proofed (`[r:health-wiring]`). |
| WS7.8 | PARTIAL | Onboarding GSTIN→Tally→bank→first-figure exists w/ dry-run imports. **"≤15 min" timed E2E never run**; GSTIN prefill is manual entry (no external GSTIN API — Human/GSP). |
| WS7.9 | DONE(core) | PWA + budgets; LCP breach found and fixed (1263–1330ms vs 2500 budget). Lighthouse-in-CI + WhatsApp send infra = Human/deferred. |
| WS7.10 | CANCELLED (owner) | English-only decision. Deviates from immutable spec — finding F2. |
| WS7.V | OPEN (HUMAN) | No validation-gate evidence logged. Required before GA by §2 P2 gate. |

### §10 WS8 · §11 WS9

WS8.1 DONE (pack + artifacts + integrity seal + anchors; only `fixed_asset_register` pending, declared in-product). WS8.2 DONE. WS8.3 DONE.
WS9.1 DONE — ✦ hardened parser, all-or-nothing commit, 4 mutation kills. **Honest caveat: "real-file corpus" = 4 realistic fixtures, not customer Tally exports; pilot files will be the real test.** WS9.2 DONE (7 bank fixtures over the generic parser). WS9.3 DONE (label + grep-gate). WS9.4 HUMAN.

### §12 WS10 · §13 WS11 · §14 QG

| Ticket | Status | Remainder |
|---|---|---|
| WS10.1 | PARTIAL | Rights workflow + legal-hold (mutation-locked) + consent gates shipped **dormant** (counsel publishes nothing yet). Human: counsel notice, rights E2E drill, tabletop, per-principal hold narrowing. |
| WS10.2 | DONE(code) | Template + alert hook + 180d journald + NTP gate, config-tested. Drill = Human. |
| WS10.3 | HUMAN | Pen test, E&O/cyber insurance, trademark, retained-CA letter — all open, all gate GA/§15. |
| WS10.4 | DONE(code) | Served/versioned/acceptance-logged, dormant until counsel publishes; disclaimer on every surface test-pinned. |
| WS10.5 | DONE | SOC2 readiness doc. |
| WS11.1 | OPEN (Human+ORCH) | No design partners recruited. **This is THE launch gate.** |
| WS11.2 | PARTIAL | Demo tenant through real services + smoke suite + support macros + CA kit. Skipped deliberately: pricing page, docs site (post-pilot GTM). Referral terms DRAFT/owner. |
| WS11.3 | OPEN | Lead-magnet micro-product not started. |
| QG.1 | PARTIAL(standing) | Gate live and CI-blocking; vector expansion continues (129 to 300, initialling F1). |
| QG.2 | PARTIAL | E2E suite authored + 8/8 green vs real stack, Lighthouse budgets pass. **Not yet in ci_gate.sh** — promotion is an ORCH decision; until promoted it does not block merges, so QG.2 as specified ("CI-blocking") is not met. |
| QG.3 | PARTIAL | ✦ 5 grep-gates live in `make gates`. **Missing from the §QG.3 list: the "'verified' strings outside the badge component" gate** — does not exist in scripts/. Small, buildable. |
| QG.4 | LIVE | This document is the first full reconciliation. Weekly cadence starts now. |

---

## 2 · Spot-check log (claims vs code — 10 checks)

1. **TDS strict-`>` boundary (WS1.C1-boundary)** — `api/app/domains/payables/payables_calc.py:79-95` carries the strict `>` with the verbatim provisos quoted; `dif/src/recompute/tds.rs:76-78` mirrors (`amount > single || aggregate_ytd + amount > aggregate`). TRUE in both engines.
2. **ESI ceil defect vector (WS1.C3)** — `ws1c_proven_defects.yaml:115` `esi_20001_gross_ceil`, expected `[15100, 65100]` paise. TRUE.
3. **Regime module (WS1.A1)** — `statutory_regime.py`: `REGIME_BOUNDARY = date(2026,4,1)`, earlier-of-credit-or-payment. TRUE.
4. **Oracle suite (WS1.E1/E2)** — run live this audit: 343 passed. Vector census: 171 total, 0 CA-initialled / 8 OWNER / 163 PENDING. TRUE (and grounds finding F1).
5. **Coverage honesty (WS3.5)** — `mahsa_coverage.json`: 9 ported, 5 explicitly unported, generation provenance note. TRUE.
6. **RBAC coverage guard (fix:rbac-api)** — `tests/integration/test_rbac_matrix.py:370` `API_ROUTE_GATES` (~135 rows) + deployed-set equality guard. TRUE.
7. **KA February ₹300 (WS2.2)** — `ws2_pt_ka.yaml:34` `pt_ka_february_300_act_33_of_2025`, expected 30000 paise, regression-locking the stale in-code table. TRUE.
8. **Parity + fuzz (WS3.2)** — `dif/tests/parity.rs` and `api/tests/integration/test_parity_fuzz.py` both exist. TRUE.
9. **QG.3 gates** — `make gates` runs exactly 5 scripts; the verified-string gate from the spec's list is absent. PARTIALLY TRUE (board understated remainder; now annotated).
10. **Daily-root anchoring (WS4.4)** — `audit_store.py:148` `compute_daily_root_for` returns the root "handed to ops for external timestamping" — external anchoring itself is not wired anywhere. Confirms the ops/Human remainder.

Board rows found overstating: **WS1.D7 `[x]`** (intra-state thresholds pending WS2 CA data) — annotated;
**line 40 WS4 row** was stale in BOTH directions (WS4.2/4.3/4.8 done but unmarked; 4.6 open) — corrected;
**WS7.6/7.7 `[ ]`** understated (both done) — corrected. No row claimed green work that does not exist.

---

## 3 · §15 launch checklist — honest render

| # | Item | Status | What remains · WHO |
|---|---|---|---|
| 1 | Oracle 300+ CA-initialled vectors green | **OPEN** | 171/300 authored (Claude, in progress); **0 CA-initialled** — retained CA initials them, or owner issues MMX-1.1 (finding F1). Both transition boundaries ARE vectored and green. |
| 2 | Five defects fixed + regression-locked; WS1.D shipped | **PARTIAL** | 5 defects: DONE, locked, re-verified. WS1.D: D5 (AATO late-fee caps — Claude) and D6 (surcharge >₹50L — Claude + CA values) still open; 6/8 shipped. |
| 3 | Mahsa parity on every ✓-path; default-healthy dead; honest-state live | **DONE** | Re-proven by this audit's live trace (§4). |
| 4 | RLS+RBAC+MFA live; red-team in CI; anchored chain; MCA doc | **CODE-DONE, HUMAN-PENDING** | RLS/RBAC live+CI; MFA active only once owner sets `MAISHA_MFA_CLAIM` (owner); daily-root **external anchoring not running** (owner/ops); route-level cross-org red-team partial (Claude, post-Supabase). |
| 5 | Entitlements 71/34/11 server-side; statutory grace | **DONE** | — |
| 6 | Today/hubs/Inbox/Audit Room; WS7.V evidence; Hinglish; lakh-crore lint | **PARTIAL** | Surfaces shipped, lint green. WS7.V: zero evidence (owner + real MSME users). Hinglish: cancelled by owner → MMX-1.1 needed (F2). |
| 7 | Tally import real-file corpus; draft-IRN labels | **CODE-DONE, PILOT-PENDING** | Fixture corpus green + labels gated; real customer Tally files arrive with pilots (owner/pilot users). |
| 8 | DPDP kit; drills; insurance; ToS/DPA; trademark | **PARTIAL** | Engineering shipped dormant. Counsel publish (counsel), breach+CERT-In drills (owner), insurance bound (owner), trademark filed (owner) — all open. |
| 9 | 10 state packs CA-verified; not-applicable proven | **PARTIAL** | 10 packs authored, NA rendering test-proven; PT sourced 7/10; zero CA verification (F1); LWF/S&E/min-wage/stamp blocked in all packs. TN-Madurai (owner's own base) blocked. |
| 10 | Partner cohort: 1 month, zero discrepancies, ≥3 CA testimonials | **OPEN** | Not started. Owner recruits (WS11.1); product is pilot-ready per this audit. |
| 11 | Billing live w/ GST self-invoicing; support staffed; SLA published | **PARTIAL** | SLA published (RULE_PACK_SLA.md). Billing blocked on Razorpay account (owner) then WS6.4 build (Claude). Support macros written; staffing = owner. |

**Fraction: 2 done · 2 code-done-human-pending · 6 partial · 1 open.**

---

## 4 · Badge-honesty spot audit (20+ figures, live trace)

Method: seeded the demo tenant via the real `api/app/dev/seed.py` against a fresh in-memory DB,
booted the **real Mahsa binary** (`dif/target/debug/mahsa`), rendered figures through the exact
assemblers/route helpers each surface serializes (`build_today`, `api_domains._figures_for`,
`api_payroll._run_figures`+live `verify_claims`, `api_filings._gstr3b_figures`+`_checks`,
`ask.answer_query`), and traced every badge. Harness: session scratchpad `badge_audit.py`.

### 4.1 The 25-row table (all PASS)

| # | Surface | Figure | Badge | Trace | Verdict |
|---|---|---|---|---|---|
| 1 | Today/cash-strip | Cash on hand | ◐ | honest-pending; 7 citation docs, all RESOLVED | PASS |
| 2 | Today/cash-strip | Monthly burn | ◐ | honest-pending; anchors resolved | PASS |
| 3 | Today/cash-strip | Runway | ◐ | honest-pending; anchors resolved | PASS |
| 4 | hub/gst | e_invoice_readiness | ◐ | unported fact key → badge_state fail-closed | PASS |
| 5 | hub/gst | filing_timeliness | ◐ | same | PASS |
| 6 | hub/gst | gstr3b_days_late | ◐ | same | PASS |
| 7 | hub/gst | gstr3b_late_fee_paise | ◐ | same | PASS |
| 8 | hub/payroll | bonus_reserve | ◐ | same | PASS |
| 9 | hub/payroll | esi_compliance | ◐ | same | PASS |
| 10 | hub/payroll | gratuity_reserve | ◐ | same | PASS |
| 11 | hub/payroll | leave_liability | ◐ | same | PASS |
| 12 | payroll/run-preview | Net pay (emp 1) | ◐ | sum-of-figures note stated verbatim | PASS |
| 13 | payroll/run-preview | PF (employee) emp 1 | **✓** | LIVE Mahsa recompute 180000==180000 paise, matches=True | PASS |
| 14 | payroll/run-preview | ESI (employee) emp 1 | **✓** | LIVE recompute 0==0 paise (above ceiling — a genuine verified nil) | PASS |
| 15 | payroll/run-preview | TDS (monthly) | ◐ | "TDS is not yet ported to Mahsa — never dressed up as ✓" | PASS |
| 16 | payroll/run-preview | Net pay (emp 2) | ◐ | sum note | PASS |
| 17 | payroll/run-preview | PF (employee) emp 2 | **✓** | LIVE recompute 180000==180000 paise | PASS |
| 18 | payroll/run-preview | Total gross | ◐ | sum note present | PASS |
| 19 | filings/gstr3b-preview | itc_setoff | **✓** | LIVE multi-value check matches=True | PASS |
| 20 | filings/gstr3b-preview | late_fee_3b | **✓** | LIVE recompute 25000 paise matches | PASS |
| 21 | filings/gstr3b-preview | interest_3b | **✓** | LIVE recompute 1700 paise matches | PASS |
| 22 | filings/gstr3b-preview | total_payable | ◐ | forever-◐ sum, note + citation present | PASS |
| 23 | ask | AP total | ◐ | fact-backed, unported → pending | PASS |
| 24 | ask | AP turnover | ◐ | same | PASS |
| 25 | ask | Dispute rate | ◐ | same | PASS |

### 4.2 Verdict-hash + chain traces

- Payroll preview verdict hash re-derived from the matched RecomputeChecks via `build_verdict`
  → deterministic, identical hash (`9b10c48c…`). The ✓ seal is recomputable, not decorative.
- GSTR-3B preview minted a verdict hash from live checks; the preview path seals
  `filing.preview` entries into the org hash chain.
- `verify_chain_for(demo-org)` → **True** (chain intact incl. the seed's sealed memory events).

### 4.3 Tamper probes (must-fail checks)

- Claimed `late_fee_3b` of **24900** paise (truth 25000): Mahsa check `matches=False`, figure
  renders **✕ unbacked** with note "MISMATCH — Maisha claimed 24900, Mahsa recomputed 25000".
  A wrong paisa cannot render ✓. PASS.
- Raw-number sweep: every figure on all 12 `/api/domains/{d}` money surfaces carries `state`
  or a T11 `restricted` shape — **zero unbadged money figures**. PASS.

### 4.4 Finding F3 (MEDIUM, latent): coverage-driven ✓ without live recompute

`ask._verdict` and hub `badge_state(key)` mint "verified" from **coverage membership alone**
(fact key ∈ ported oracle targets) with no per-request Mahsa call (`ask.py:176` folds without
`recompute_claims`; docstring admits "No new Mahsa call"). Empirically checked this audit:
**zero fact keys across all 12 domain snapshots collide with the 9 ported target names**, so no
surface renders such a ✓ today — every rendered ✓ in the product currently comes from a live
`verify_claims` recompute. But the invariant is unenforced: a future snapshot fact named e.g.
`itc_setoff` would render ✓ without Mahsa recomputing that number. Remedy (small): a CI test
asserting `set(enrich(snapshot)) ∩ PORTED == ∅` for every domain, or thread live claims through
the ask fold. Until then this is one naming collision away from a §0.4 breach.

**Badge audit conclusion: 0 dishonest badges. No CRITICAL finding.**

---

## 5 · Cut-list review vs §2 untouchables

Cut/deferred this program: i18n/Hinglish (owner-cancelled), pricing page + docs site (WS11.2),
CITE.P1-4 xlsx locator, Lighthouse-in-CI, WhatsApp send infra, WS4.6 NestJS promotion,
WS2.4 state expansion, per-tenant pack-version display, GSTIN-API prefill.

- §2 permits cutting **breadth (states, languages, integrations)** — every cut above is breadth
  or infra-promotion, none is P0, oracle, tenancy, or §0.4. **No untouchable was cut.** PASS.
- The only P0-adjacent items not green are **BLOCKED-CA / open**, not cut: WS1.A2/A3, D5, D6,
  E2 initialling. They remain on the board as open — deferral is visible, not silent. PASS.
- Watch item: the Hinglish cancellation is an owner **deviation recorded against the immutable
  spec**, not a permitted cut under §2 (languages were "English + Hinglish" in a P2 ticket and
  §15). It needs MMX-1.1 to be legitimate (F2).

---

## 6 · Board corrections applied this pass

1. WS4 row: WS4.2/4.3/4.8 marked done (were unreconciled `[ ]`), WS4.6 explicitly open,
   WS4.4 external-anchoring remainder noted.
2. WS7 row: WS7.6 and WS7.7 marked done (were `[ ]`); WS7.4 and WS7.8 marked `[~]` with the
   honest remainders (altitude toggle; 15-min timed onboarding).
3. WS1.D7 annotated (intra-state thresholds pending CA state data).
4. QG.3 annotated: 5 gates live, verified-string gate still missing.
5. QG.4 marked `[~]` — first reconciliation done, weekly standing.

---

## 7 · Priority queue coming out of this reconciliation

1. **Owner decision (F1):** retained-CA engagement (WS10.3 already lists the letter) or MMX-1.1
   amending the CA-initialling language. Blocks §15 items 1 and 9 permanently otherwise.
2. **Claude, small:** F3 invariant test (fact-key × ported-target non-collision) — one test.
3. **Claude:** WS1.D5 AATO late-fee caps (engine currently overstates fees for small taxpayers —
   a wrong-direction-for-trust defect on a money figure, even though always ◐-badged).
4. **Claude:** QG.3 verified-string grep-gate; QG.2 promotion decision into ci_gate.sh;
   WS4.8 deliberate-red canary PR.
5. **Owner:** MAISHA_MFA_CLAIM config, daily-root external anchoring, Razorpay, insurance,
   trademark, counsel publish, WS11.1 partner recruitment — the entire remaining launch path
   is now owner-side or CA-side, not code-side.

— END OF RECONCILIATION 2026-07-23 —
