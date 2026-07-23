# PROGRESS BOARD — checkbox mirror of MMX-1.0 (ORCH maintains)

Governing spec: `docs/MASTER_PLAN.md` (immutable). Detail log: `PROGRESS.md`.
`[x]` DONE · `[~]` WIP · `[c]` BLOCKED-CA · `[h]` BLOCKED-HUMAN · `[ ]` not started.

## Governance
- [x] GOV — spec at docs/ (444), tracking files, CODEOWNERS, CI guard

## P0 · Law & Trust
### WS1.A — Income-tax Act 2025 dual regime
- [x] WS1.A1 statutory_regime module (OPUS) — selector + form map + Tax Year; payment codes BLOCKED-CA
- [c] WS1.A2 citation re-point (SONNET) — BLOCKED-CA: needs 1961→2025 section map
- [c] WS1.A3 return artifacts (SONNET) — BLOCKED-CA: needs CA fixtures
### WS1.B — Labour Codes engine
- [x] WS1.B1 wage-definition engine (OPUS) — engine + PF/ESI/bonus wiring done, vector-locked
- [x] WS1.B2 hybrid gratuity (OPUS) — gratuity_hybrid + 3 vectors; boundary year-apportionment flagged for CA
- [x] WS1.B3 CTC validator (SONNET) — validator + rebalance suggester, never mutates; 8 tests
- [ ] WS1.B4 citation sweep (SONNET)
### WS1.C — Five proven defects
- [x] WS1.C1 194J 30k→50k
- [x] WS1.C2 194I per-month ₹50k
- [x] WS1.C3 ESI ceil-before-truncate + anti-pattern gate
- [x] WS1.C4 115BAA 25.168% + MAT excluded
- [x] WS1.C5 vault retention 8y from FY-end
### WS1.D — Missing sections & GST completeness
- [x] WS1.D1 194Q/194T/TCS/206AA-AB (spec values in; TCS-goods/206AA floors BLOCKED-CA)
- [x] WS1.D2 QRMP · [x] D3 CMP-08 · [x] D4 IMS · [ ] D5 late-fee caps(ported+Rust) · [ ] D6 surcharge(CA) · [x] D7 e-way · [x] D8 MSME Form-1
### WS1.E — Oracle & rule packs
- [x] WS1.E1 oracle framework (seeded with defect vectors)
- [~] WS1.E2 expand to 300+ CA-initialled vectors (21 seeded: 7 WS1.C + 6 WS1.A + 4 WS1.B-wage + 4 WS1.B-wiring/gratuity, all ca_initials PENDING)
- [ ] WS1.E3 rule-pack versioning

## P0/P3 · WS2 state packs · WS3 Mahsa recomputation
- [ ] WS2.1–2.4
- [x] WS3.1 Rust recompute port (6 paths, parity harness; itr/regime/retention still Python-only)
- [x] WS3.2 parity gate — vector-parity (tests/parity.rs) + live /fold recompute BLOCK + randomized Py↔Rust fuzz (tests/integration/test_parity_fuzz.py, ~5100 seeded paise-granular cases/run over 9 targets incl. multi-value itc)
- [x] WS3.3 kill default-healthy · [x] WS3.4 verdict object · [x] WS3.5 honest-state wiring (coverage json + tri-state badges)

## P1 · Platform (WS4 tenancy · WS5 RBAC · WS6 entitlements)
- [x] WS4.1 tenancy schema+RLS · [~] WS4.7 red-team suite (DB/RLS layer; route-level awaits WS4.3) · [x] WS4.5 tenant-iterated jobs (per-org failure isolation + org+job+period idempotency) · [ ] WS4.2–4.4/4.6/4.8 (board not yet reconciled with 07-21 PROGRESS entries)
- [x] WS5.1 RBAC · [x] WS5.2 approval matrices · [x] WS5.3 per-role landing   ·   [x] WS6.1 entitlements · [x] WS6.2 quantity gates · [x] WS6.3 upgrade triggers · [h] WS6.4 billing(Razorpay=Human)
- [x] WS4.4 per-tenant hash-chain + MCA audit-trail doc

## P2 · Product & UX (WS7 · WS8 · WS9)
- [x] WS7 UX research · [x] WS7.1 design tokens+lakh/crore · [x] WS7.2 Verified-Number chip · [x] WS7.3 Today view · [x] WS7.5 Exception Inbox · [ ] WS7.4/7.6-7.8 · [x] WS7.9 PWA core (manifest/SW/offline-staleness/responsive-360/budget; Lighthouse-in-CI + template-send infra deferred to Human) · [h] WS7.10 i18n (deferred, English-only for now) · [ ] WS7.V  · [x] WS8.1 audit pack · [x] WS8.2 query threads+sampling · [x] WS8.3 CA seat (free+unlimited, invite→accept, referral events)  · [ ] WS9.1 · [x] WS9.2 bank parsers · [x] WS9.3 · [h] WS9.4 GSP

### SPA core-loop (batch-2, from the P2-ROUND gap scout)
- [x] P0-1 filing flow (b1:filing-flow, 2026-07-22): /file queue + preview→typed-confirm→receipt over require_filing-gated JSON wrappers, T5 attempt-evidence export; WS7 contract T5 row ✅
- [x] P0-2 generic action preview/commit (api_actions two-step + HMAC token + ActionDrawer; invariant 9 both sides)
- [x] P0-3 entry forms (b2:entry-forms, 2026-07-22): customer/invoice (GST split badged), vendor/bill (tds_engine section+rate+amount badged), multi-line journal (double-entry 422 w/ totals), employee/salary structure (PF/ESI/PT + s.2(y) warning); `lines` field type + WS7.4 keyboard (Enter advances/adds rows, chord previews/confirms)
- [x] P0-4 payroll run flow (b2:payroll-run, 2026-07-22): /payroll-run screen + preview→typed-confirm over the EXISTING run_payroll write (per-employee PF/ESI live-verified, TDS/net ◐); draft run lands in the EXISTING approvals queue via payroll_run_pending metric + PAYROLL-005 (rule pack 2026.07.1), decision releases/voids it (resolve_pending_runs hook in record_decision); payslip/Form16/ECR behind export-gated /api routes
- [x] P0-5 treasury CSV re-import (b2:csv-reimport, 2026-07-22): Onboarding's bank-CSV dry-run→confirm extracted to components/BankCsvImport.tsx (ONE parser/preview, both call sites use it — Onboarding step 2 unchanged behaviourally); mounted on the treasury Domain.tsx screen behind a new `GET /api/treasury/accounts` read route (RBAC-matrixed) so re-import can target a real existing account; confirm import → onImported → domain refetch refreshes badged figures. Fixed a latent bug while extracting: the shared import fetch was missing `authHeaders()` (bearer JWT), so it now attaches the same header every other call gets.
- [x] P1-5 financial statements screens (a:statements, 2026-07-22): /statements tabs (TB/P&L/BS/GL drilldown) over new read-only api_statements.py assembler (badge_state-badged figures, api_domains pattern); imbalance + BS-equation failures are explicit banners with the server's exact diff; GL running-balance table paise-exact + payload-badged; plain @media print; +2 RBAC-matrixed read routes
- [x] P1-1 Ask Maisha SPA screen (a:ask, 2026-07-22): /ask question box → answer card, POST /api/ask threading verbatim through the EXISTING app.core.ask.answer_query pipeline (zero drift from the HTMX page); every figure through the EXISTING VerifiedNumber, tri-state fails closed to unbacked on anything unrecognised; read-only, +1 RBAC-matrixed route
- [x] P1-7 field-level RBAC masking (a:field-rbac, 2026-07-22): contract T11 row — salary_detail sensitivity class + FIELD_SENSITIVITY map + ONE mask_field/mask_figures helper on the EXISTING can_view_sensitivity lattice (no second clearance system); applied at the /api serialization boundary (payroll per-employee figures for non-Owner/Admin/Accountant, forecast margin/unit-economics for Investor, generic domain-figure assembler); masked field -> {restricted, reason} with the value ABSENT from the body, byte-level integration asserts; SPA LockChip renders the restriction + reason (hidden-not-absent honoured)
- [x] P1-2 Audit Room parity in SPA (b:audit-room, 2026-07-23): AuditRoom.tsx grows CA query threads (list/raise/respond-with-doc/resolve on the EXISTING WS8.2 /api/audit/threads CRUD; enabled/disabled-with-reason from the payload's server-computed can_respond, seal refs shown per event), deterministic sampling view (spec form → /api/audit/sample → voucher table w/ vault doc bundle refs, seed shown), and pack .zip/.pdf downloads rendered ONLY on payload can_export; server tweak = threads_json now carries can_respond/respond_denied_reason/can_export (can() convention from api_payroll)
- [x] P1-8 expense claim + receipt OCR (a:expense-ocr, 2026-07-22): submit-claim (already registered round-3) extended with a policy-limit WARNING surfaced in the preview text + an optional vendor_gstin field; POST /api/expense/ocr-receipt thin-wraps the EXISTING ExpenseService.ocr_capture the HTMX route already uses (one parser, proven identical); ActionDrawer gained an optional `prefill` (schema-scoped overlay only) + a fixed "parsed from receipt — check before submitting" caveat, still the same editable-field/preview-then-confirm gate; Domain.tsx mounts a receipt-photo capture (accept="image/*" capture) above the expense form only, remounting it per parse via a nonce key; +1 RBAC-matrixed route. Root-cause fix along the way: api_actions.py's commit route was missing the `role` arg api_domains._figures_for's other 2 call sites already pass (WS5.1 T11 drift) — fixed at the one call site.
- [x] P1-3 CA seat invite/accept UI (b:ca-invite, 2026-07-23): /settings route (Shell nav appended) with a CA seat section over the EXISTING WS8.3 endpoints — invite-by-email form (POST /api/ca/invite) + the free-and-unlimited entitlement fact STATED, not re-derived (it's real by SEAT_EXEMPT_ROLES exemption); pending-invites list needed a new GET /api/ca/pending (app/core/ca_seat.list_pending, same manage_users gate as invite, +1 RBAC-matrixed row, lifecycle test extended: owner sees the invite, Accountant 403s, list empties on accept). Non-owner disabled-with-reason derived from the route's own 403 (mirrors PayrollRun's ConfirmFailure pattern) — no second, inventable copy of the role table. /ca/accept lands the invited CA on their own screen; POST /api/ca/accept already matches on the caller's VERIFIED token email+org (no URL token exists or is needed — identity IS the authorization, per the existing WS8.3 design), success redirects to /audit (Role.CA's landing). A 404 (no pending invite for this account) renders as an honest sentence, not the failure-mode ErrorState. Split into router-free presentational pieces (CaInviteForm/PendingInvitesList/CaAcceptCard) so they render via the repo's existing no-@testing-library renderToStaticMarkup convention; the hooked wrappers (Settings/CaSeatSection/CaAccept) own useQuery/useMutation and stay untested directly, matching every other SPA screen in this repo. Tests: vitest Settings.test.tsx (12) + CaAccept.test.tsx (10) — non-owner disabled reason, canSubmitInvite/inviteErrorText edge cases, empty/populated pending list, idle/pending/404/500/success card states; py: +1 API_ROUTE_GATES row + 3 new lifecycle assertions in test_ca_invite_accept_lifecycle_and_referral_events (10/10 green). Gates (isolated to this ticket's files; other tickets are landing in this same tree concurrently): ruff+mypy clean on touched .py; tsc -b clean repo-wide; new/touched vitest files 22/22 green in isolation and green again inside a full `vitest run` (266/267 — the 1 failure is Ask.test.ts, untracked WIP from a concurrent sibling ticket, confirmed unrelated via git diff); oxlint src exit 0 (pre-existing fast-refresh warnings only, no new warning kind). No new deps.
- [x] P1-6 connection-health strip + figure staleness (b:health-strip, 2026-07-23): Approvals-only `useConnectionHealth`/`booksFreshness` lifted — `ConnectionHealthStrip` mounted once in Shell.tsx (visible on every screen, quiet when healthy, native `<details>` popover onto the full panel); `booksFreshness`/`ago`/`useNow` moved to `lib/freshness.ts` (Approvals re-exports, PayrollRun/Filings imports unchanged); Today.tsx's `CashStrip` and Domain.tsx's `FigureGrid` now thread real connection-health/payload-age staleness into their happy-path figures (previously only downgraded on `mahsa_up:false`/request-error). Mutation-proofed vitest on both.
  - [x] r:health-wiring (2026-07-23) closed the verifier FAILs: added wiring-level tests that render Today()/Domain() themselves (not just CashStrip/FigureGrid) so hard-coding `stale={false}` at the real call sites fails a test; new Shell.test.tsx pins the ConnectionHealthStrip mount; honesty fix — `booksFreshness`'s check-itself-failed case now returns `stale: "unknown"` (the existing `Freshness` type) instead of a false `stale: true`, so the copy says "we could not check" rather than asserting staleness as fact. vitest 308/308, tsc -b clean, oxlint clean.
- [x] P1-4 CFO strategy in SPA (b:cfo-strategy, 2026-07-23): /cfo route — scenario runner on existing POST /api/forecast/scenario (◐-badged hypothetical cards; null-runway honesty extends the WS7-E2E fix: empty form / provably-not-burning / burning-past-horizon each get their own honest sentence, never ∞), cap table on existing GET /api/equity/cap-table (tabular category/% table + ESOP pool + honest-empty; SAFE converter over the existing pure-compute /api/equity/safe/convert, "no stored register" stated), investor update via new thin POST /api/investor/preview wrapper (app/web/api_investor.py) over the SAME strategy.investor_update generator — badge_state-badged figures, raw runway_months+accounts so Domains.runwayText is reused verbatim, send stays HTMX (link-out; router exposes no send route, test-pinned). +1 RBAC-matrixed row; py 3/3 + vitest 17/17

## P3/P4 · Hardening, GTM (WS10 · WS11)
- [ ] WS10.1–10.5  · [ ] WS11.1–11.3

## Standing quality gates
- [~] QG.1 statutory-oracle gate (framework live; expand vectors)
- [ ] QG.2 Playwright/Lighthouse · [~] QG.3 grep-gates (truncate-then-round live) · [ ] QG.4 weekly reconciliation
