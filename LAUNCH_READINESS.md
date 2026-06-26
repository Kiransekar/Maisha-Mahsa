# Maisha-Mahsa — Launch Readiness Roadmap

> **Purpose.** This is the ordered, do-one-at-a-time checklist that takes the project from
> *"the engine works, but only one web page exists"* to **launch-ready for real-world use**.
> Work it **top to bottom**. Do not start a task until every task above it is ✅.
>
> **Scope decision (2026-06-16).** v1 ships as the **deterministic dashboard product** —
> auth, data entry, the 12 domain pages, reports, alerts, deployment. The conversational
> **LLM ("Maisha") chat layer is explicitly deferred to Phase 8** and is *optional* for launch.
> Deployment target: **single VPS + Docker Compose + Caddy** (the scaffold already in `infra/`).
>
> **This doc does not replace the rules.** `CLAUDE.md` is still *how* we build; the PRD
> (`maisha_mahsa_v4_full_suite_prd.md`) is still *what* we build; `BUILD_PROGRESS.md` is still
> the truth of what's green. This file is the **sequence** that connects them to a launch.

---

## 0. How to use this document

- Each task has a stable **ID** (e.g. `P1-AUTH`), a **What**, a **Why**, the **files it
  touches**, a **Done when** acceptance test, and the **Verify** command that must pass.
- A task is **done only when `make verify` is green** *and* its `BUILD_PROGRESS.md` row / domain
  `manifest.py` feature is flipped to ✅ / `DONE`, per `CLAUDE.md` §5. No vacuous passes, no
  silent skips, exact paise math, every rule cited. (`CLAUDE.md` §2.)
- After finishing a task, **commit** with the task ID in the message and tick its box below.
- If a task reveals the PRD is wrong, amend the PRD explicitly and note it in
  `BUILD_PROGRESS.md` (per the doctrine) — do not silently diverge.

### The non-negotiable gate (runs after every task)

```bash
make verify      # ruff + mypy + cargo clippy -D warnings + cargo test + pytest
```

It must print `✅ verify passed`. If it doesn't, the task is not done.

---

## 1. Current state (verified 2026-06-16)

**What genuinely works (✅, tested — 169 Python + 52 Rust tests green):**

- **Mahsa** (Rust DIF core): `/health`, `/fold`; fold → validate → unfold; 23 cited rules;
  property tests. Deterministic, no clock/RNG/network inside fold.
- **The loop** (`api/app/core/loop.py`): DB snapshot → Mahsa fold/validate/unfold → hash-chained
  audit entry. This is the Golden-Rule choke point and it is real.
- **All 12 domain *backends*** — exact paise math, statutory calculators, domain rules, JSON
  APIs under `/api/<domain>/...`, unit + integration tested.
- **Home dashboard** (`/`): KPI strip, 12 domain-health cards (live from Mahsa), compliance
  calendar, approvals queue. Degrades gracefully if Mahsa is down.
- **Email**: pure composers + inline-styled templates (daily brief, compliance alert, payroll
  approval, investor update); pluggable transport (InMemory / SMTP→MailHog).
- **Infra scaffold**: `infra/docker-compose.yml` (dif/api/redis/mailhog/ollama), `Caddyfile`,
  both Dockerfiles. **Not yet built/run/validated.**

**What is missing — why the app feels empty (the work in this doc):**

| Gap | Evidence | Phase |
|---|---|---|
| **No authentication** | `app_password` in `config.py` is never enforced; no login, no session, all routes open | P1 |
| **No schema migrations** | Schema created via `Base.metadata.create_all` (dev only); no Alembic | P1 |
| **No web UI for any domain** | Only `/` renders HTML. Nav links are `/#<domain>` anchors to nothing. The 12 domains are JSON-API-only | P2 |
| **No way to get data in via the browser** | CSV import / invoices / bills / journals are all raw API calls; a real user can't use them | P2 |
| **No audit-trail viewer** | The hash chain exists but nothing surfaces it to a human | P2 |
| **Per-domain feature backlog** | Each `manifest.py` has `NOT_STARTED` features (e-invoice/IRN, ECR/Form-16, 26AS recon, MCA filings, OCR pipelines, …) | P3 |
| **Mahsa critic is a stub** | `dif/src/critic.rs` — prior update not implemented (L1 row ⬜) | P4 |
| **No scheduler** | Redis is in compose but no ARQ worker; the 8pm brief & T-7/T-1/T-0 alerts are composed but never dispatched on a schedule | P5 |
| **No production hardening** | No input-size limits, error pages, rate limiting, audit-verify endpoint, observability | P6 |
| **Backups / restore / runbook** | restic + runbook not done (I3 ⬜) | P6 |
| **Never deployed** | compose/Caddy unproven; no TLS host; no secrets management | P7 |
| **No parallel-run sign-off** | 1-month parallel run (I2 ⬜) | P9 |
| **LLM "Maisha" chat layer absent** | No ollama/anthropic client wired anywhere in `api/` | P8 (deferred) |

---

## 2. Roadmap at a glance

| Phase | Theme | Outcome | Blocking for launch? |
|---|---|---|---|
| **P1** | Foundation gaps | Safe to hold real data: auth, migrations, secrets, first-run | **Yes** |
| **P2** | The web product | A human can drive all 12 domains in the browser + see the audit trail | **Yes** |
| **P3** | Domain feature backlog | Every PRD feature per domain implemented (manifests all `DONE`) | **Yes** |
| **P4** | Mahsa completion | Critic implemented; rule set complete | **Yes** |
| **P5** | Automation & channels | Scheduler dispatches briefs + statutory alerts; real SMTP | **Yes** |
| **P6** | Hardening for real money | Validation, audit-verify, backups, observability, security review | **Yes** |
| **P7** | Deployment | Live on a VPS behind Caddy TLS, secrets managed, smoke-tested | **Yes** |
| **P8** | LLM "Maisha" chat (optional) | Conversational CFO assistant, gatekept by Mahsa | No (deferred) |
| **P9** | Parallel run & go-live | 1-month parallel run + runbook + sign-off | **Yes (final)** |

---

## Phase 1 — Foundation gaps (make it safe to hold real data)

> Until this phase is done, **do not put real financial data in the app.** No auth + no
> migrations = a regulatory liability waiting to happen.

### [x] P1-AUTH — Single-user authentication ✅ (2026-06-26)
> Done: stdlib-HMAC signed cookie (no new dep), login guard middleware over all routes except
> /health, /login, /static; `/login` + `/logout`; `login.html`; `app.core.auth`; tests in
> `tests/integration/test_auth.py`. ponytail: single-user; audit identity stays the founder.
- **What.** Implement the single-user password login from PRD §11.1. Login page → verify against
  `MAISHA_APP_PASSWORD` → signed, HTTP-only session cookie → middleware/dependency that
  protects every route except `/health`, `/login`, and `/static/*`.
- **Why.** Financial data behind an open port is unacceptable. The acting user must also be the
  real authenticated identity stamped into the audit log (`loop.py` currently hardcodes
  `user_id="founder"`).
- **Touches.** `api/app/core/auth.py` (new), `api/app/deps.py` (add `require_session`),
  `api/app/main.py` (mount middleware, add `/login` + `/logout`),
  `api/app/web/templates/login.html` (new), `api/app/config.py` (add `session_secret`).
- **Done when.** Unauthenticated request to `/` → 302 to `/login`; wrong password → error,
  no cookie; correct password → cookie set, `/` renders; audit entries carry the logged-in user.
- **Verify.** New `api/tests/integration/test_auth.py` covering all four cases; `make verify` green.

### [x] P1-MIGRATE — Alembic migrations (stop using create_all) ✅ (2026-06-26)
> Done: `api/alembic/` + `alembic.ini`; baseline `0001_baseline` builds the full 41-table
> schema from `Base.metadata` (can't drift); `main.py` only auto-creates when
> `MAISHA_ENVIRONMENT != production`; `make migrate`; tests in `test_migrations.py` assert
> every table is built and `compare_metadata` shows zero drift.
- **What.** Add Alembic; generate the baseline migration from the current models; switch the app
  to *not* auto-create in production (keep create_all only behind a `MAISHA_DEV=1` flag).
- **Why.** `CLAUDE.md` §3 L2 lists Alembic as ⬜. `create_all` silently ignores schema drift —
  fatal for a system that must reproduce historical numbers. Migrations make schema changes
  auditable and reversible.
- **Touches.** `api/alembic/` (new), `api/alembic.ini` (new), `api/app/main.py` (gate create_all),
  `api/pyproject.toml` (add `alembic`), `Makefile` (add `make migrate`).
- **Done when.** `alembic upgrade head` builds the full 40+ table schema on an empty DB and
  matches `schema.sql`; `alembic revision --autogenerate` on an unchanged model set is empty.
- **Verify.** A test that runs `upgrade head` on a temp DB and asserts every model table exists;
  `make verify` green. Flip `BUILD_PROGRESS.md` L2 Alembic row to ✅.

### [x] P1-SECRETS — Config hardening & `.env.example` ✅ (2026-06-26)
> Done: `api/.env.example` documents every MAISHA_* var; `auth.assert_production_secrets`
> refuses to boot with default password/session-secret when MAISHA_ENVIRONMENT=production.
> Remaining nicety: move SQLite to a backed-up path — folded into P6-BACKUP.
- **What.** Add `infra/.env.example` documenting every `MAISHA_*` var; make the app **refuse to
  start in non-dev mode** if `MAISHA_APP_PASSWORD`/`session_secret` are still defaults; move the
  SQLite file to a configured, backed-up path.
- **Why.** `change-me` reaching production is the single most likely catastrophic mistake.
- **Touches.** `api/app/config.py` (startup validation), `infra/.env.example` (new),
  `infra/docker-compose.yml` (reference `.env`), `README.md` (point to it).
- **Done when.** App with default secrets + `MAISHA_DEV` unset fails fast with a clear message;
  with real secrets it boots.
- **Verify.** Unit test on the config validator; `make verify` green.

### [x] P1-FIRSTRUN — Seed / demo data path & empty-state UX ✅ (2026-06-26)
> Done: `app/dev/seed.py` (dev-gated, idempotent) + `make seed` loads a realistic seed-stage
> startup — bank account + 3 months of txns, 2 customers + invoices (one overdue), 2 vendors
> + bills (one past its MSME 45-day clock), 2 employees + salary structures, a cap table.
> `test_seed.py` asserts non-zero cash/burn/AR/AP and idempotency. Empty-state polish on the
> 12 domain pages is a minor follow-up (dashboard already has it; figure tables show ₹0 rows).
- **What.** A `make seed` (or `/api/dev/seed`, dev-gated) that loads a realistic sample company
  (a few bank txns, invoices, bills, employees, a cap table) so screens show real numbers; and
  ensure every empty screen has a clear "no data yet — add some" state (the dashboard already
  does this; extend to domain pages as they land in P2).
- **Why.** Today every KPI is ₹0.00, which is indistinguishable from "broken." A seed path makes
  development, demos, and QA sane.
- **Touches.** `api/app/dev/seed.py` (new, dev-gated), `Makefile` (`make seed`).
- **Done when.** Fresh DB + `make seed` → dashboard shows non-zero cash/burn/AR/AP and at least
  one amber/red somewhere to prove the status system renders.
- **Verify.** Seed runs idempotently in a test; `make verify` green.

---

## Phase 2 — The web product (the 12 missing pages + data entry + audit)

> This is the biggest visible gap. Build the **reference page first**, get it pixel-perfect
> (`skills/ui-polish`), then clone its shape for the other 11. **One domain per task.**

### [ ] P2-SCAFFOLD — Shared domain-page scaffold
- **What.** A reusable Jinja layout + HTMX patterns for a domain page: header, KPI sub-strip,
  data tables, "add" forms (modal or inline), a **"Run through Mahsa"** action that calls the
  domain `fold` and renders the returned banners/status/color, and inline validation errors.
  Add real anchor sections or real routes so the nav stops pointing at nothing.
- **Why.** Every domain page shares this skeleton; building it once keeps them consistent and
  enforces the Golden Rule visually (the status the user sees comes from Mahsa, not Python).
- **Touches.** `api/app/web/templates/domain/_layout.html` + partials (new),
  `api/app/web/static/css/app.css`, `api/app/web/static/js/` (HTMX helpers),
  `api/app/web/templates/base.html` (fix nav links).
- **Done when.** A throwaway domain page using the scaffold renders header + a table + an "add"
  form + a Mahsa-status panel, with green/amber/red per `skills/ui-polish`.
- **Verify.** Render test for the partials; manual screenshot reviewed against `skills/ui-polish`.

### [ ] P2-D01-treasury — Treasury page (REFERENCE — do this one *thoroughly*)
- **What.** HTML page at `/treasury`: bank-account list + **CSV upload form** (HDFC/ICICI/Axis/
  canonical), consolidated cash position, burn, runway; "Run through Mahsa" panel; link to the
  audit trail filtered to treasury. Wire the GET HTML route in `treasury/router.py`.
- **Why.** PRD reference slice; `BUILD_PROGRESS.md` D01 Router/UI is 🟡. Everything else copies it.
- **Touches.** `api/app/domains/treasury/router.py` (add HTML GET), `api/app/web/templates/
  domain/treasury.html` (new).
- **Done when.** Upload a sample CSV in the browser → cash/burn/runway update → Mahsa status
  shows; an integration test drives the full page loop.
- **Verify.** `api/tests/integration/test_treasury_page.py`; `make verify` green; D01 Router/UI → ✅.

### [ ] P2-D02…D12 — One page per remaining domain
Repeat the P2-D01 pattern for each. **Each is its own task / commit / DoD / `make verify`.**

- [ ] **P2-D02-revenue** — customers, invoice creation form (intra/inter GST), AR aging, dunning view
- [ ] **P2-D03-payables** — vendors, bill entry, 3-way match status, AP aging, MSME clock, ITC
- [ ] **P2-D04-payroll** — employees + salary structure, payroll-run preview, **approval gate UI**
- [ ] **P2-D05-gst** — GSTIN validate, GSTR-3B / GSTR-1 builders, ITC reconcile view
- [ ] **P2-D06-tax** — advance-tax 234C schedule, TDS-return view, TDS summary
- [ ] **P2-D07-ledger** — journal entry form (balanced-or-reject), trial balance, P&L, balance sheet
- [ ] **P2-D08-forecast** — budget vs actual, cash projection chart, scenario inputs, unit economics
- [ ] **P2-D09-equity** — cap table, ESOP pool (board-approval gate), SAFE conversion, snapshots
- [ ] **P2-D10-compliance** — statutory calendar, seed deadlines, file-status, alert window
- [ ] **P2-D11-expense** — claim form, approval workflow, policy-check result, receipt parse, analytics
- [ ] **P2-D12-vault** — document upload (hash/dedup), classification, retention, search, integrity

> For each: add the HTML GET route, the template using the P2-SCAFFOLD, the forms that POST to
> the existing `/api/<domain>/...` endpoints, the Mahsa-status panel, and **one integration test
> exercising the page through the real loop** (`CLAUDE.md` §5.5). Flip the domain's
> `BUILD_PROGRESS.md` Router/UI cell and `manifest.py` UI feature.

### [ ] P2-AUDIT — Audit-trail viewer
- **What.** A page at `/audit` listing audit entries (filterable by domain/date), showing the
  hash chain and a **"verify chain"** button that recomputes `this_hash = sha256(prev || canonical_json(entry))`
  end-to-end and shows ✅/tamper-detected.
- **Why.** The hash chain is the product's compliance backbone; it must be inspectable by a human.
- **Touches.** `api/app/web/templates/audit.html` (new), a router (new `audit_router.py`),
  reuse `core/audit*.py`.
- **Done when.** Entries render; verify button passes on a clean chain and fails loudly on a
  tampered row (tested by mutating one row in a test DB).
- **Verify.** `api/tests/integration/test_audit_view.py`; `make verify` green.

### [ ] P2-NAV — Wire navigation & dashboard deep-links
- **What.** Update `base.html` nav and dashboard cards to link to the now-real domain pages and
  `/audit`; add the CFO brief (`/cfo/brief.html`) to the nav.
- **Done when.** Every nav item and every dashboard card links to a real, rendering page (no 404,
  no dead anchors). **Re-screenshot the app and confirm visually.**
- **Verify.** A test that GETs every nav target and asserts 200; `make verify` green.

---

## Phase 3 — Domain feature backlog (finish every PRD feature) ✅ COMPLETE (2026-06-26)

> All 12 domain manifests are now 100% — **116/116 features DONE**. The final 16 were built in
> 2026-06-26: payroll pt/lwf/leave; payables recurring/payment_run; equity share_certificates/
> rights_buyback; forecast rev_recognition_forecast; revenue export_invoicing; expense card_recon;
> vault access_control; compliance secretarial/audit_support/dpiit; tax itr/transfer_pricing.
> External-system boundaries (ITR e-filing portal upload, IRP/GSP QR-signing) are computed up to
> the boundary and documented as out-of-scope for the on-prem app.

> Each domain's `manifest.py` still lists `NOT_STARTED` features. Real-world use means these are
> done, not just the "core." Work **one feature at a time**, Rust fold/rule first (if it needs
> one), then Python service + exact paise math + tests, then UI, then `make verify`
> (`CLAUDE.md` §5). Below is the backlog distilled from `BUILD_PROGRESS.md` + manifests — treat
> each bullet as a task and check it off.

- [ ] **treasury** — burn attribution by category; auto-sweep/FD-laddering suggestions; UPI recon; bank-guarantee tracking
- [ ] **revenue** — revenue recognition/deferred; IRN + QR (e-invoice); export/LUT; dunning email dispatch
- [ ] **payables** — recurring payables; early-pay discount; payment run
- [ ] **payroll** — ECR file; payslip PDF; Form-16; LWF; leave management
- [ ] **gst** — e-invoice; RCM; GSTR-9; HSN master; LUT
- [ ] **tax** — s.234B; 26AS reconciliation; ITR prep; 80-IAC holiday; transfer pricing
- [ ] **ledger** — GL view; cash-flow statement; bank reconciliation; auto journal posting from other modules
- [ ] **forecast** — headcount → payroll forecast; quarterly re-forecast; revenue-recognition timing
- [ ] **equity** — convertible notes; investor-reporting generator; dividends (s.123); share certificates; rights/buyback
- [ ] **compliance** — MCA filings (AOC-4/MGT-7/DIR-3/DPT-3); secretarial; audit-support package; DPIIT
- [ ] **expense** — OCR image pipeline (Tesseract); card reconciliation; mileage/per-diem
- [ ] **vault** — OCR image pipeline; auto-archive; RBAC

> **Statutory note (`CLAUDE.md` §2 "every rule cited", `skills/indian-fin-rules`).** Every new
> calculation that enforces law needs a `statute` + `section` in `dif/rules/rules.yaml` and a
> property test. Re-verify statutory constants (rates, thresholds, ceilings) against the current
> Finance Act before flipping a feature to `DONE`.
>
> **Done-domain rule.** A domain is "done" when *every* `manifest.py` feature is `DONE`, its
> Rust fold/rules + property tests are green, its UI renders, ≥1 integration test crosses the
> real loop, and `make verify` is green — then its `BUILD_PROGRESS.md` Status flips 🟡 → ✅.

---

## Phase 4 — Mahsa engine completion

### [ ] P4-CRITIC — Implement the critic (prior update)
- **What.** Replace the `dif/src/critic.rs` stub with the real prior-update step from the PRD
  (the feedback that refines intent priors). Keep it **deterministic** — no clock/RNG/network;
  inject any time as a parameter (`CLAUDE.md` §2).
- **Why.** L1 "Mahsa: critic" is ⬜; it's part of the DIF contract.
- **Touches.** `dif/src/critic.rs`, `dif/src/lib.rs`, `dif/tests/` (proptest invariants).
- **Done when.** Critic updates priors deterministically; property tests prove same-input →
  same-output and the documented invariants hold.
- **Verify.** `make test-rust` + `make verify` green; flip L1 critic row to ✅.

### [ ] P4-RULES — Rule-set completeness pass
- **What.** Audit `dif/rules/rules.yaml` against every feature shipped in P3; ensure each
  enforced obligation has a cited rule + property test; no orphan rule IDs vs `domains/*/rules.py`.
- **Done when.** Every Python `rules.py` ID maps to a YAML rule and vice-versa; `skills/indian-fin-rules`
  matrix is satisfied.
- **Verify.** A cross-check test (Python rule IDs ⊆ YAML rule IDs); `make verify` green.

---

## Phase 5 — Automation & channels

### [ ] P5-WORKER — ARQ worker on Redis
- **What.** Add an ARQ (or equivalent) worker service that runs scheduled jobs. Redis is already
  in compose.
- **Touches.** `api/app/worker.py` (new), `infra/docker-compose.yml` (worker service),
  `api/pyproject.toml` (`arq`).
- **Done when.** Worker boots, connects to Redis, runs a no-op heartbeat job on schedule.
- **Verify.** Integration test enqueues a job and asserts it ran; `make verify` green.

### [ ] P5-BRIEF — Schedule the 8pm CFO brief
- **What.** Cron-schedule `EmailChannel.send_daily_brief` for 20:00 IST via the worker.
- **Why.** U3 says "cron scheduling pending."
- **Done when.** A job fires at the configured time (test with an injected clock) and sends the
  rendered brief through the configured transport.
- **Verify.** Test with InMemoryTransport asserts the brief was queued at the right time; `make verify` green.

### [ ] P5-ALERTS — Statutory alert dispatch (T-7 / T-1 / T-0 / overdue)
- **What.** Schedule the compliance-alert emails off the statutory calendar.
- **Done when.** Given a seeded deadline, the worker dispatches the correct alert at T-7/T-1/T-0
  and an overdue alert after.
- **Verify.** Test with injected dates + InMemoryTransport; `make verify` green.

### [ ] P5-SMTP — Real SMTP configuration
- **What.** Document and validate real SMTP (`MAISHA_SMTP_*`) for production; MailHog stays for dev.
- **Done when.** A staging send reaches a real inbox; defaults still target MailHog locally.
- **Verify.** Manual staging send confirmed; config documented in `.env.example`.

---

## Phase 6 — Hardening for real money

### [ ] P6-VALIDATION — Input limits & robust error handling
- **What.** Request-size limits (esp. CSV/document uploads), strict Pydantic validation on every
  body, friendly HTML error pages (400/404/500), and a global exception handler that never leaks
  stack traces to the user but always writes the failure to logs.
- **Done when.** Oversized/malformed inputs are rejected with clear messages; no unhandled 500s
  in the happy paths; tested.
- **Verify.** Tests for oversized upload, malformed body, forced exception; `make verify` green.

### [ ] P6-AUDITVERIFY — Audit-chain integrity check (endpoint + scheduled)
- **What.** An endpoint + a scheduled job (P5 worker) that walks the full audit chain and alerts
  if any link is broken; surfaces status on the dashboard.
- **Why.** Tamper-evidence is only useful if something actually checks it.
- **Done when.** Clean chain → ✅; injected tamper → alert + dashboard banner; tested.
- **Verify.** Test mutates a row and asserts detection; `make verify` green.

### [ ] P6-BACKUP — Backup & restore (restic) + restore drill
- **What.** Automated encrypted backups of the SQLite DB (and document store) with restic;
  a **documented, tested restore drill**.
- **Why.** I3 ⬜. A finance product without a proven restore is not launchable.
- **Touches.** `infra/backup/` (restic scripts + cron), `RUNBOOK.md` (new).
- **Done when.** Backup runs on schedule; a restore from backup reproduces the DB byte-for-byte
  (or row-for-row) on a clean box; drill documented.
- **Verify.** Restore drill performed and recorded in `RUNBOOK.md`.

### [ ] P6-OBSERVABILITY — Logs, health, basic metrics
- **What.** Structured logging, a `/health` that also checks DB + Mahsa reachability, and a
  minimal metrics/uptime signal.
- **Done when.** Logs are structured and rotate; `/health` reflects real dependency status.
- **Verify.** Test for `/health` degraded state when Mahsa is down; `make verify` green.

### [ ] P6-SECREVIEW — Security review of the whole surface
- **What.** Run `/security-review` (and a manual auth/session/upload/SQL review) over the
  full app before exposing it to the internet.
- **Done when.** No high/critical findings open; medium findings triaged with notes.
- **Verify.** Review output attached to the launch checklist.

---

## Phase 7 — Deployment (single VPS + Docker + Caddy)

### [ ] P7-COMPOSE — Build & validate the full stack locally
- **What.** `make dev` (`docker compose up --build`) brings up dif + api + redis + mailhog +
  worker; run the full smoke path against the containers (login → seed → drive a domain → brief).
- **Why.** The compose/Dockerfiles have never been built/run; prove them before the VPS.
- **Done when.** All services healthy in Docker; smoke path passes against `localhost:8000`.
- **Verify.** Documented smoke run; screenshots of the running app.

### [ ] P7-VPS — Provision the VPS & deploy
- **What.** Provision the box, install Docker, copy `infra/`, set real `.env` secrets, `docker
  compose up -d`, persist volumes on a backed-up disk.
- **Done when.** Stack runs on the VPS, survives reboot (`restart: unless-stopped`), data on a
  persistent volume.
- **Verify.** `curl https://<host>/health` from outside returns ok (after P7-TLS).

### [ ] P7-TLS — Caddy + domain + TLS
- **What.** Point the real domain at the box; set it in `infra/Caddyfile`; Caddy auto-provisions
  TLS; only 80/443 exposed publicly (api/redis/mailhog bound to localhost or firewalled).
- **Done when.** `https://<domain>` serves the login page with a valid cert; HTTP redirects to HTTPS.
- **Verify.** SSL Labs / `curl -vI https://<domain>` clean; ports audited.

### [ ] P7-PRODSMOKE — Production smoke test
- **What.** Full path on production: login → enter a small real dataset → run each domain →
  confirm Mahsa status + audit entries → receive the 8pm brief.
- **Done when.** Every step passes against production; audit chain verifies.
- **Verify.** Documented prod smoke run signed off.

---

## Phase 8 — LLM "Maisha" conversational layer (OPTIONAL — deferred, post-launch)

> Not required for v1. Build only after P1–P7 are live and stable. Implements PRD's chat
> assistant **without ever violating the Golden Rule**: the LLM may propose, but every number it
> emits is recomputed by Mahsa before a human sees it (`CLAUDE.md` §1, §7).

- [ ] **P8-LLM-CLIENT** — LLM client (Ollama local first; `claude-opus-4-8`/`claude-sonnet-4-6`
  fallback only when explicitly enabled). Pull a local model (`ollama pull …`). *(Confirm current
  model IDs against the `claude-api` skill before wiring API fallback.)*
- [ ] **P8-CHAT-LOOP** — query → LLM drafts intent/answer → **Mahsa recomputes & gatekeeps** →
  render. The LLM never emits a final number Mahsa hasn't validated; every turn is audited.
- [ ] **P8-CHAT-UI** — chat surface in the dashboard with the Mahsa status/banners attached to
  every answer.
- [ ] **P8-GUARDRAILS** — prompt-injection defense, refusal handling, full audit of LLM I/O.

> DoD: same as any module — exact paise at the edge, every shown number Mahsa-validated, tests +
> `make verify` green, integration test through the real loop.

---

## Phase 9 — Parallel run & go-live (final gate)

### [ ] P9-PARALLEL — 1-month parallel run
- **What.** Run Maisha-Mahsa alongside the existing process/accountant for one month; reconcile
  every figure; log discrepancies and resolve each to zero. (I2 ⬜, PRD §L6.)
- **Done when.** A full month with **zero unresolved numeric discrepancies**.
- **Verify.** Reconciliation log attached; sign-off recorded in `BUILD_PROGRESS.md`.

### [ ] P9-RUNBOOK — Operations runbook
- **What.** Complete `RUNBOOK.md`: deploy/upgrade, backup/restore (from P6-BACKUP), rotate
  secrets, incident response, statutory-constant update procedure, on-call basics. (I3 ⬜.)
- **Done when.** A second person can operate the system from the runbook alone.
- **Verify.** Runbook dry-run by someone other than the author.

### [ ] P9-SIGNOFF — Launch checklist (the binary gate)
All must be ✅ before go-live:

- [ ] `make verify` green on the release commit
- [ ] P1–P7 + P9 all complete; `BUILD_PROGRESS.md` has no 🟡/⬜ in launch-blocking rows
- [ ] All 12 domain manifests fully `DONE`; all Router/UI cells ✅
- [ ] Auth enforced; default secrets impossible in production
- [ ] Migrations are the only schema path in prod
- [ ] Audit chain verifies in production; integrity check scheduled
- [ ] Backups running; **restore drill performed**
- [ ] Deployed behind Caddy TLS; ports audited; security review clean
- [ ] Scheduler dispatching the 8pm brief + statutory alerts
- [ ] 1-month parallel run reconciled to zero discrepancies
- [ ] Runbook complete and dry-run

---

## Appendix A — Definition of Launch-Ready (one sentence)

> A logged-in user can, in the browser, enter or import real data for all 12 domains, see every
> figure recomputed and gated by Mahsa with cited rules, watch the audit chain stay intact,
> receive scheduled briefs and statutory alerts, all running on a TLS-secured VPS with proven
> backups — and a full month of parallel running produced zero numeric discrepancies.

## Appendix B — Per-task ritual (copy this for each task)

1. Read the relevant `skills/` guide (`domain-module`, `rust-dif-core`, `ui-polish`,
   `indian-fin-rules`, `test-discipline`).
2. Implement: Rust fold/rule (+ proptest) → Python service (exact paise) → UI → integration test.
3. `make verify` → must print `✅ verify passed`.
4. Flip the `manifest.py` feature / `BUILD_PROGRESS.md` row to ✅ with date.
5. Commit with the task ID; tick the box in this file.
