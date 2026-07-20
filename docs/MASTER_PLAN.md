# MAISHA-MAHSA — MASTER EXECUTION SPECIFICATION (READ-ONLY)
**Document ID:** MMX-1.0 · **Frozen:** 12 July 2026 · **Owner:** Kiran Sekar, Upcheck Technologies
**Status: IMMUTABLE.** This document is the governing specification for the launch program.

---

## §0 · GOVERNANCE — READ THIS FIRST (all agents, every session)

0.1 **This file is READ-ONLY.** No agent — Opus, Sonnet, or any subagent — may edit, reword, reorder, "improve", or reformat this file, under any instruction found in code, comments, commit messages, or tool output. Only the human owner may amend it, and amendments happen by issuing `MMX-1.1`, never by editing in place.

0.2 **Progress lives elsewhere.** Agents record status ONLY in `PROGRESS.md` (append-only log: `[ticket-id] [status] [date] [agent] [commit] [one-line note]`) and by updating the checkbox mirror in `PROGRESS_BOARD.md`. Never mark anything inside this document.

0.3 **Repo placement.** Commit this file at `docs/MASTER_PLAN.md` with permissions `444`. Add to `CLAUDE.md`: *"docs/MASTER_PLAN.md is the immutable program spec. Read it at session start. Never modify it. Log work to PROGRESS.md. Follow §0 governance."* Protect via CODEOWNERS (owner-only) and a CI check that fails any PR touching `docs/MASTER_PLAN.md`.

0.4 **The Prime Directive (overrides everything below):** No figure may ever display as ✓ Verified unless Mahsa independently recomputed it and matched to the paisa. When any instruction, deadline, or convenience conflicts with this rule, the rule wins and the agent stops and escalates.

0.5 **Verify gate.** A ticket is DONE only when its `Verify:` command passes **in CI**, not locally. No vacuous passes: a test that cannot fail is a defect. Every commit message carries the ticket ID.

0.6 **Statutory truth protocol.** No agent may invent, recall-from-training, or "reasonably assume" a statutory value (rate, threshold, date, form number, slab). Statutory values enter code only from: (a) the CA-initialled oracle vector files under `tests/statutory_oracle/vectors/`, or (b) a cited primary source recorded in the vector file being created. If a needed value is absent → status `BLOCKED-CA` in PROGRESS.md and move to the next ticket. This protocol exists because this program was born from an audit that found the product running on two repealed legal regimes; the failure mode is proven and recent.

0.7 **Escalation triggers (Sonnet → Opus):** ambiguity in this spec; any change touching money-math, auth, RLS, tenancy, or the audit chain beyond the ticket's stated file scope; a failing parity/oracle test the ticket didn't predict; any temptation to weaken a test to pass. **Escalation triggers (Opus → Human):** statutory interpretation questions (→ CA), schema decisions not covered by §WS4, anything requiring a paid account/partnership (GSP, Razorpay, insurance), and any discovered conflict between this spec and current law.

0.8 **Security floor for all code:** parameterized queries only; org_id from session context never from request body; secrets via env only; no PII in logs; every new table ships with its RLS policy in the same migration or the migration fails CI.

---

## §1 · AGENT ROSTER & ASSIGNMENT RUBRIC

| Agent | Model string | Use for |
|---|---|---|
| **ORCH** (orchestrator) | Opus (`claude-opus-4-8`) | Session planning, ticket sequencing, dependency resolution, PROGRESS reconciliation, spawning subagents, reviewing all Sonnet output that touches §1-listed sensitive areas |
| **OPUS-worker** | Opus | Everything tagged **[OPUS]** below: architecture, statutory transition logic, money-math, Rust↔Python parity, RLS/auth/tenancy, migrations, oracle vector derivation, security-sensitive code, root-causing subtle failures |
| **SONNET-worker** (parallelize 2–4) | Sonnet (`claude-sonnet-4-6`) | Everything tagged **[SONNET]** below: implementation from a written spec, UI components from the design system, data-pack plumbing, i18n wiring, templates/PDFs/exports, test-writing from given vectors, seeds, docs, CRUD, entitlement middleware per spec |

**Rubric when a ticket is unlabeled or new:** assign Opus if ANY of: touches money computation, statutory logic, auth/RLS/tenancy, audit chain, cross-language parity, schema, or has >1 plausible design. Otherwise Sonnet. Sonnet never self-upgrades scope; it escalates (§0.7).

**Working agreement:** Opus writes `SPEC-<ticket>.md` design notes for anything it hands to Sonnet; Sonnet implements to the spec letter; ORCH reviews diffs on sensitive paths before merge. Recommended session pattern: ORCH plans the day from PROGRESS.md → dispatches parallel Sonnet tickets with no shared files → serializes Opus tickets on shared cores.

---

## §2 · PHASE MAP & HARD GATES

| Phase | Tickets | Gate (binary, CI-proven) |
|---|---|---|
| **P0 Law & Trust** (wk 1–8) | WS1.*, WS3.*, QG.1–3 | Oracle suite green under 1961/2025 regimes + Labour-Code vectors; Rust↔Python paisa-parity on all ported paths; CA sign-off rows present in vectors |
| **P1 Platform** (wk 5–14) | WS4.*, WS5.*, WS6.* | Tenancy red-team suite green; entitlement matrix tests green; MFA+RBAC E2E green |
| **P2 Product & UX** (wk 9–20) | WS7.*, WS8.*, WS9.1–2 | U-validation gates (§WS7.V) passed with logged evidence |
| **P3 Hardening & Partners** (wk 16–26) | WS2.*, WS10.*, WS11.1 | Pen-test clean; insurance bound; partner cohort: 1 month, zero unresolved numeric discrepancies |
| **P4 GA** (wk 26–30) | WS11.* | §9 launch checklist 100% |

Cut-list rule under pressure: cut breadth (states, languages, integrations) — NEVER P0, oracle, tenancy, or §0.4.

---

## §3 · WS1 — STATUTORY CORRECTNESS & FRESHNESS

### WS1.A — Income-tax Act 2025 dual regime
- **WS1.A1 [OPUS]** Design `statutory_regime` module: regime selector keyed on credit/payment date (boundary 2026-04-01, earlier-of-credit-or-payment rule); `regime_1961` frozen namespace; `regime_2025` with s.392/393/394 structure, payment-code table (1001–1067), form map (16→130, 16A→131, 24Q→138, 3CD→26, 15G/H→121), "Tax Year" labeling. Output: `SPEC-WS1A.md` + core module. *Done-when:* boundary vectors (credit Mar/pay Apr; advance Mar/credit Apr) resolve to the correct regime. *Verify:* `pytest tests/statutory_oracle -k regime`.
- **WS1.A2 [SONNET]** (deps A1) Re-point every rule citation, docstring, UI string, and PDF template from 1961 sections/forms to the regime-aware map. No hardcoded "192"/"194x"/"Form 16" outside `regime_1961`. *Verify:* CI grep-gate `scripts/check_no_stale_citations.sh` green.
- **WS1.A3 [SONNET]** (deps A1) Regenerate return artifacts: Form 138 (ex-24Q) layout, Form 130/131 certificates, challan payment codes. Formats from CA-provided samples in `tests/statutory_oracle/fixtures/` only (§0.6). *Verify:* artifact snapshot tests.

### WS1.B — Labour Codes engine (regime in force 21-11-2025)
- **WS1.B1 [OPUS]** Wage-definition engine per Code on Wages s.2(y): wages = Basic+DA+retaining; if excluded allowances (incl. overtime) > 50% of total remuneration, add excess back; remuneration-in-kind up to 15% counts. Expose `statutory_wage_base(ctc_components) -> Paise`. All PF/ESI/gratuity/bonus/leave-encashment call this. *Done-when:* Ministry-FAQ worked examples (as oracle vectors) reproduce exactly. *Verify:* `pytest -k wage_base`.
- **WS1.B2 [OPUS]** Hybrid gratuity: pre-21-11-2025 service under old base, post under new, FTE eligibility ≥1 year; transitional computation per MoLE FAQs. *Verify:* `pytest -k gratuity_hybrid`.
- **WS1.B3 [SONNET]** (deps B1) CTC validator + auto-rebalance suggester in salary-structure feature (warn ◐ when Basic+DA < 50%; propose compliant restructure; never silently alter). *Verify:* unit + UI integration tests.
- **WS1.B4 [SONNET]** Citation sweep: EPF&MP Act 1952 / ESI Act 1948 / Bonus Act 1965 / Gratuity Act 1972 → Code on Wages 2019 / SS Code 2020 refs in `rules.yaml`, UI, PDFs. Add compliance-calendar watch item: gratuity-insurance mandate (date-to-be-notified) and state Labour-Code rules tracker. *Verify:* grep-gate + rules.yaml schema test.

### WS1.C — The five proven defects (regression-locked)
- **WS1.C1 [SONNET]** 194J threshold 30k→50k (both single and aggregate keys). *Verify:* oracle vector `tds_194j_fy2526`.
- **WS1.C2 [OPUS]** 194I per-month restructure: threshold ₹50,000 **per month or part thereof**, TDS on the full month's rent when crossed; replace annual-aggregate logic; month-granular tracking in `tds_on_payment` and vendor ledger. *Verify:* vectors incl. the ₹40k/mo-no-TDS and ₹55k/mo-full-TDS cases.
- **WS1.C3 [OPUS]** ESI rounding: apply ceil on the exact Decimal product BEFORE any int truncation (both legs); audit the whole codebase for the truncate-then-round anti-pattern (`int(Decimal(...)*rate)`) and fix every instance. *Verify:* vector gross=20001→(151,651); anti-pattern grep-gate.
- **WS1.C4 [OPUS]** Company tax: 115BAA path = 22% + **10% surcharge** + 4% cess (25.168%), MAT **excluded** on this path; non-115BAA path = normal rates + MAT 15% comparison; caller chooses regime explicitly. *Verify:* vectors both paths.
- **WS1.C5 [SONNET]** Vault retention: statutory class → 8 years computed **from FY-end**, not upload date; migration for existing records; auto-archive respects new dates. *Verify:* retention vectors + migration test.

### WS1.D — Missing sections & GST completeness
- **WS1.D1 [OPUS]** 194Q (0.1% purchases >₹50L/vendor/FY, interplay with TCS 206C(1H): TDS primacy), 194T (10%, partner payments >₹20k), TCS s.394 goods, 206AA/206AB higher-rate ladder. Design note first (`SPEC-WS1D1.md`), values via §0.6. *Verify:* per-section vector files.
- **WS1.D2 [OPUS]** QRMP: filing-profile entity attribute (monthly | QRMP | composition); QRMP → quarterly GSTR-1/3B + monthly PMT-06 (fixed-sum 35% or self-assessed) + IFF; calendar, late-fee, and interest logic per profile. *Verify:* QRMP vectors + calendar tests.
- **WS1.D3 [SONNET]** (deps D2) CMP-08 quarterly artifact for composition profile. *Verify:* snapshot test.
- **WS1.D4 [SONNET]** IMS workflow: inward-invoice accept/reject/pending states feeding ITC eligibility; UI in GST hub Altitude-2. *Verify:* state-machine tests.
- **WS1.D5 [SONNET]** AATO-linked GSTR late-fee caps (≤1.5Cr→₹2k; 1.5–5Cr→₹5k; >5Cr→₹10k; nil→₹500); AATO as entity attribute. *Verify:* cap vectors.
- **WS1.D6 [SONNET]** Payroll surcharge >₹50L (10/15/25% ladder, 25% cap new regime, marginal relief at each step — vectors from CA) + s.208 ₹10k de-minimis in 234B/C. *Verify:* surcharge vectors.
- **WS1.D7 [OPUS]** E-way bill: threshold engine (₹50k inter-state; per-state intra thresholds from WS2 packs) + compliant JSON artifact; "prepare-and-download, not filed" labeling. *Verify:* threshold matrix tests + JSON schema validation.
- **WS1.D8 [SONNET]** MSME Form-1 half-yearly data pack from existing 45-day tracker (Apr–Sep due 31 Oct; Oct–Mar due 30 Apr). *Verify:* fixture-driven snapshot.

### WS1.E — Oracle & rule packs (the institution)
- **WS1.E1 [OPUS]** `tests/statutory_oracle/` framework: vector schema `{id, statute, section, citation_url, ca_initials, ca_date, inputs, expected}`; runner executes vectors against Python AND (where ported) Rust; CI-blocking. Seed with the 69 audit-harness checks (corrected to law). *Verify:* framework self-test + seed green.
- **WS1.E2 [SONNET]** (continuous, deps E1) Expand to 300+ vectors across all domains incl. transition boundaries (31-03/01-04-2026 tax; 20/21-11-2025 gratuity) and adversarial cases. Every vector BLOCKED-CA until initialled — Sonnet drafts, CA confirms, only then unblocked (§0.6). 
- **WS1.E3 [OPUS]** Rule-pack versioning: packs as signed data (rules + constants + UI copy strings), tenant-visible version banner, changelog, staged rollout flag, published SLA doc (Budget day / GST Council / CBDT / MoLE). *Verify:* pack-load tests + rollback test.

---

## §4 · WS2 — STATE-WISE COMPLIANCE (data packs, not code)

- **WS2.1 [OPUS]** State-pack schema & loader: `states/<code>.yaml` carrying PT (slabs, periodicity incl. half-yearly & municipal variants, registration types PTRC/PTEC), LWF (amounts, due months), S&E (registration, renewal, leave defaults), minimum-wage tables (feeds bonus cap = max(₹7,000, sched. min wage) and Labour-Code floor checks), share-certificate stamp duty (rate + deadline), intra-state e-way threshold, Labour-Code state-rules status. **Explicit `not_applicable` blocks — a silent ₹0 is a defect (render "Not applicable in <state>").** *Verify:* schema validation + not-applicable rendering tests.
- **WS2.2 [SONNET]** (deps 2.1) Author packs for launch set: MH, KA, **TN (half-yearly PT, corporation-wise slabs — includes owner's own Madurai base)**, TS, AP, GJ, WB, DL, HR, UP. Every numeric value BLOCKED-CA until initialled. *Verify:* per-state vector files green post-CA.
- **WS2.3 [SONNET]** Wire packs into payroll (PT/LWF/min-wage), compliance calendar (S&E, stamp-duty deadlines), equity (stamp duty), e-way (thresholds); tenant state selection in onboarding; per-tenant pack-version display. *Verify:* integration tests per consumer.
- **WS2.4 [SONNET]** Expansion backlog: remaining PT states (KL, MP, OD, BR, JH, AS, PB, SK, NE, PY), LWF to ~16 states — same BLOCKED-CA protocol; publish state roadmap page content.

---

## §5 · WS3 — MAHSA TRUE RECOMPUTATION (Prime Directive engineering)

- **WS3.1 [OPUS]** Port order (each its own PR): slab tax+surcharge → PF/ESI incl. wage-floor → TDS engine (all sections) → ITC set-off → GST late-fee/interest → gratuity/bonus. Rust implementations pure, clock-free, integer-paise. *Verify:* `cargo test` + parity below.
- **WS3.2 [OPUS]** Parity gate in validate: Python figure vs Rust recomputation to the paisa; mismatch → BLOCK verdict with both values + diagnostic; parity fuzz tests (proptest randomized inputs) per path. *Verify:* `tests/parity/` green incl. fuzz.
- **WS3.3 [OPUS]** Kill default-healthy: missing domain signal → degraded/blocked, never 1.0; snapshot completeness check. *Verify:* absence-behavior tests.
- **WS3.4 [OPUS]** Verdict object: {figures, rule-pack version, org_id binding, hash} — consumed by UI badges, PDF seals, audit chain. *Verify:* verdict schema + binding tests.
- **WS3.5 [SONNET]** (deps 3.1–3.4) Honest-state wiring: any path not yet ported renders ◐ everywhere (UI/PDF/API); coverage report `mahsa_coverage.json` drives it automatically. *Verify:* coverage-driven badge tests.

---

## §6 · WS4 — MULTI-TENANT PLATFORM (Supabase/Vercel)

- **WS4.1 [OPUS]** Target schema design (`SPEC-WS4.md`): org → entity → **gstin_registration** (G6: multi-GSTIN scoped ledgers/ITC/returns) → domain tables; BIGINT paise; RLS policy per table on org_id from JWT claims; storage prefix scheme. *This spec precedes all P1 code.*
- **WS4.2 [OPUS]** (deps 4.1) Migration engineering: Alembic→Postgres replay; SQLite tenant importer (existing parallel-run data) with checksum reconciliation report. *Verify:* import round-trip equality test.
- **WS4.3 [OPUS]** Auth: Supabase Auth (email/phone OTP, Google), MFA enforced for Owner/Admin/Approver, session policies; delete the HMAC-cookie system. *Verify:* auth E2E suite.
- **WS4.4 [OPUS]** Per-tenant hash-chain genesis; daily chain-root external timestamp anchoring; `/audit/verify` per tenant; edit-log formalization on every accounting record (non-disablable) → MCA audit-trail conformance doc `docs/AUDIT_TRAIL_COMPLIANCE.md`. *Verify:* chain tests + tamper-detection test.
- **WS4.5 [SONNET]** (deps 4.1) Scheduled jobs to cron/Edge Functions (brief, dunning, alerts, audit-verify) tenant-iterated with per-tenant failure isolation. *Verify:* job idempotency tests.
- **WS4.6 [OPUS]** Backend promotion: api-nest to main line; Python retained as CI oracle cross-check (calculator outputs diffed in CI); archive plan for divergences. *Verify:* cross-language calculator diff suite green.
- **WS4.7 [OPUS]** Tenancy red-team suite: authenticated cross-org access attempts against every route and storage path, run in CI forever. *Verify:* `tests/redteam/` green.
- **WS4.8 [SONNET]** CI/CD assembly: full gate (oracle + cargo + parity + pytest/jest + redteam + E2E) on GitHub Actions blocking main; Mahsa binary built in CI so no loop test can skip. *Verify:* a deliberately-broken canary PR fails each gate.

---

## §7 · WS5 — RBAC

- **WS5.1 [OPUS]** Role model + policy layer: Owner, Admin, Accountant (no money/filing approvals), Approver (matrix-limited), CA (read-only Audit Room + queries; payroll as registers), Investor-link (time-boxed, watermarked, report-scoped). Server-side checks + RLS backing; role events → audit chain. *Verify:* permission matrix test (every role × every route).
- **WS5.2 [SONNET]** (deps 5.1) Approval matrices: fixed defaults (Basics/Startup), configurable role×amount×action (Growth); statutory-filing actions always require Owner/Admin. *Verify:* matrix-driven E2E.
- **WS5.3 [SONNET]** Per-role landing (Owner→Today, Accountant→Exception Inbox, CA→Audit Room) + vault sensitivity classes wired to roles. *Verify:* routing + visibility tests.

---

## §8 · WS6 — TIER ENTITLEMENTS

- **WS6.1 [OPUS]** Entitlement architecture: feature registry (116 domain + platform keys) → plan map (Basics 71 / Startup +34 / Growth +11 per the agreed split, stored as data); middleware + RLS-safe enforcement; **statutory-grace override** (never block a legal filing mid-flow — grace + log + upsell after). *Verify:* full-matrix entitlement tests incl. grace path.
- **WS6.2 [SONNET]** (deps 6.1) Quantity gates (headcount 10/50/fair-use-200, seats, entities): soft-warn → grace → block-with-upgrade; locked features visible with reason + trigger (never hidden). *Verify:* limit E2E.
- **WS6.3 [SONNET]** Upgrade-trigger events: employee #11 → Bonus/Gratuity pitch; first SAFE → Equity; AATO ₹5Cr → e-invoice add-on; second GSTIN → Growth; board meeting → secretarial. *Verify:* event-emission tests.
- **WS6.4 [SONNET]** Billing: Razorpay subscriptions; your own GST-compliant invoices (18%) generated through the product's invoicing engine (dogfood). *Verify:* billing sandbox E2E. *(Account setup = Human.)*

---

## §9 · WS7 — UI/UX BUILD (per the research report; read frontend-design conventions before any component work)

- **WS7.1 [OPUS]** Design-system foundation: token architecture with **verification family (teal/indigo + shield ✓/◐/✕ icons) strictly separate from money-direction green/red**; tabular numerals; **lakh/crore grouping util used by every money renderer (CI lint: no raw toLocaleString)**; Indic font companions; light+dark; component states inventory. Output tokens + `SPEC-WS7.md`. 
- **WS7.2 [SONNET]** (deps 7.1, WS3.4) Verified Number chip + Working panel (inputs→formula→citations→documents→verdict hash→report-issue) + the ◐→✓ lock-in micro-interaction. *Verify:* Storybook states + interaction tests.
- **WS7.3 [SONNET]** Today view: cash strip · Needs-you queue · Trouble radar (alert grammar: what/when/₹-consequence/one-tap) · penalties-avoided counter. *Verify:* Playwright E2E.
- **WS7.4 [SONNET]** Five hubs, two altitudes, per-role default + remembered toggle; Altitude-2 keyboard-flow data entry (Tally-speed). *Verify:* hub E2E per domain.
- **WS7.5 [SONNET]** Exception Inbox (Needs document / Needs categorization / Mahsa blocked / Awaiting approval / Feed broken; bulk ops with preview). *Verify:* queue E2E.
- **WS7.6 [OPUS]** High-stakes approval flow (restated verified totals → typed/biometric confirm → audit receipt) — Opus because it composes auth+verdicts+chain. *Verify:* approval E2E incl. tamper case.
- **WS7.7 [SONNET]** Connection-health strip + stale-data badge downgrade ("as of {date}"). *Verify:* staleness tests.
- **WS7.8 [SONNET]** Onboarding: GSTIN prefill → bank CSV → Tally import → 5 questions → first verified artifact ≤15 min; empty states everywhere. *Verify:* onboarding E2E timed.
- **WS7.9 [SONNET]** Mobile PWA (Today/approvals/alerts/receipt-capture/Ask Maisha) with ₹10k-Android perf budget (Lighthouse budget in CI); WhatsApp brief/alert templates with deep-link approvals (confirm in-app only). *Verify:* Lighthouse CI + template snapshot tests.
- **WS7.10 [SONNET]** i18n layer from day one; English + Hinglish strings (transliteration-first per research: "GST bharna hai" register; statutory nouns stay English); string-extraction lint. *Verify:* i18n coverage check.
- **WS7.V [Human+ORCH]** Validation gates before GA (evidence logged in PROGRESS): 5-second test 8/10 MSME owners; first-invoice <4 min low-end Android; **badge comprehension test**; weekly CA design hour minutes; approval-friction A/B (confidence, not speed, is the metric).

---

## §10 · WS8 — CA AUDIT ROOM

- **WS8.1 [SONNET]** (deps WS5, WS4.4) Audit Pack generator: TB/P&L/BS/GL/FAR/statutory registers/GST+26AS recons/MSME ageing — every figure badged + evidence-linked; Excel+PDF; audit-chain integrity certificate embedded. *Verify:* pack snapshot + link-integrity tests.
- **WS8.2 [SONNET]** Query threads pinned to entries (raise→respond-with-doc→resolve, all chained); sampling helper (selection → voucher+doc bundle). *Verify:* thread E2E.
- **WS8.3 [SONNET]** CA seat onboarding (free, unlimited) + referral instrumentation. *Verify:* invite E2E + event tests.

---

## §11 · WS9 — INTEGRATIONS

- **WS9.1 [OPUS]** Tally XML import: masters, opening balances, vouchers; mapping UI for unmatched ledgers; checksum reconciliation report the user approves before commit. (#1 activation feature; Opus for the mapping-ambiguity design.) *Verify:* real-file corpus round-trip tests.
- **WS9.2 [SONNET]** Bank CSV parsers: existing 3 + SBI, Kotak, Yes, IndusInd, IDFC, Federal, RBL (fixture-driven). *Verify:* per-bank fixtures.
- **WS9.3 [SONNET]** Draft-IRN honesty pass: every local IRN surface labelled "DRAFT — not IRP-registered; not a valid e-invoice until registered", incl. PDFs and QR captions. *Verify:* label grep-gate + snapshots.
- **WS9.4 [Human]** GSP partnership scoping (e-invoice/e-way/filing rails) — post-revenue decision; AA feeds post-launch.

---

## §12 · WS10 — COMPANY-LEVEL COMPLIANCE, SECURITY, LEGAL

- **WS10.1 [OPUS]** DPDP engineering: consent/notice capture (Rule-3 grade) in onboarding + employee-data ingestion; rights workflow (access/correct/erase, 90-day SLA tracking); **legal-hold matrix** (erasure vs 8-year books retention, basis logged); breach runbook implementing two-stage DPBI + 72-hour principal notice; processing-log retention ≥1 year. Target: demonstrably compliant well before 13 May 2027. *Verify:* rights-workflow E2E + runbook tabletop (Human).
- **WS10.2 [SONNET]** CERT-In posture: 6-hour incident-report template + alerting hook, 180-day log retention config, NTP sync in infra. *Verify:* config tests + drill (Human).
- **WS10.3 [Human]** Pen test (external) before GA; **E&O/professional-indemnity + cyber insurance bound before first paying customer**; trademark filing; retained-CA engagement letter.
- **WS10.4 [SONNET]** Legal kit implementation: ToS/privacy served + versioned + acceptance-logged; in-product and PDF disclaimers ("software tool, not the practice of chartered accountancy; outputs require professional verification"); DPA template with sub-processor annex (Supabase, LLM, email). *(Drafts reviewed by human counsel before ship.)* *Verify:* acceptance-log tests.
- **WS10.5 [SONNET]** SOC 2 Type I readiness backlog (12-month roadmap doc; control mapping to existing audit chain).

---

## §13 · WS11 — GTM READINESS

- **WS11.1 [Human+ORCH]** Design-partner cohort (5 MSMEs, 10 startups, 5 CA firms) recruited during P2; each runs one-month parallel with existing books; discrepancy log to zero = the launch gate.
- **WS11.2 [SONNET]** Demo tenant with rich seeded data (all hubs alive, badges everywhere); pricing page; docs site skeleton; WhatsApp-first support macros; CA channel kit (Audit Room walkthrough + referral terms). 
- **WS11.3 [SONNET]** Free lead magnet: standalone compliance-calendar + WhatsApp deadline alerts micro-product sharing the calendar engine.

---

## §14 · QUALITY GATES (standing, CI-blocking from P0)

- **QG.1 [OPUS]** Statutory-oracle gate (WS1.E1) — blocks every merge.
- **QG.2 [SONNET]** Playwright E2E per hub happy-path + approval flows; Lighthouse budgets.
- **QG.3 [SONNET]** Grep-gates: stale citations, truncate-then-round anti-pattern, raw number formatting, missing RLS on new tables, "verified" strings outside the badge component.
- **QG.4 [ORCH]** Weekly: PROGRESS reconciliation vs this spec; cut-list review against §2's untouchables; badge-honesty spot audit (sample 20 rendered figures → trace verdicts).

---

## §15 · LAUNCH CHECKLIST (binary; ORCH maintains mirror in PROGRESS_BOARD.md)

☐ Oracle 300+ CA-initialled vectors green (both tax regimes, Labour Codes, GST/QRMP, both transition boundaries) ☐ Five defects fixed + regression-locked; WS1.D features shipped ☐ Mahsa parity on every ✓-path; default-healthy dead; honest-state wiring live ☐ RLS+RBAC+MFA live; red-team in CI; per-tenant anchored audit chain; MCA audit-trail doc ☐ Entitlements enforce 71/34/11 server-side; statutory-grace works ☐ Today/hubs/Inbox/Audit Room shipped; §WS7.V gates passed with evidence; Hinglish live; lakh-crore lint green ☐ Tally import passes real-file corpus; draft-IRN labels everywhere ☐ DPDP kit live; breach+CERT-In drills done; insurance bound; ToS/DPA/disclaimers shipping; trademark filed ☐ 10 state packs CA-verified; not-applicable rendering proven ☐ Partner cohort: 1 month, zero unresolved discrepancies, ≥3 CA testimonials ☐ Billing live with GST self-invoicing; support staffed; rule-pack SLA published

---

## §16 · RISK REGISTER (ORCH reviews weekly)

1. **A ✓ badge is ever wrong in production** → existential. Controls: §0.4, oracle, parity, staged rule-pack rollout, public correction log.
2. **Statutory churn** — three regime changes in 12 months is the proven base rate. Controls: rule-packs-as-data, CA retainer, notification-day SLAs, state-rules watchlist, §0.6.
3. **Cross-tenant leak** → existential. Controls: RLS+API+verdict-binding, red-team in CI, pen test, insurance.
4. **Agent-induced drift** — models "helpfully" adjusting statutory values or tests. Controls: §0.6 truth protocol, BLOCKED-CA states, grep-gates, ORCH sensitive-path review, this document's immutability.
5. **CA channel misfire.** Controls: "eases the CFO's battles" positioning; free seats; Audit Room makes the CA look good; never "replace your CA."

— END OF MMX-1.0 · READ-ONLY —
