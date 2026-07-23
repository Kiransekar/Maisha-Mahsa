# DEPLOYMENT — launch runbook (launch-pack, 2026-07-22)

The owner personally configures backend, database and hosting. This runbook is the complete
self-serve path; every step below was verified against the code it names (file references
inline). Steps that need an external account you own are marked **OWNER-STEP** with exactly what
to enter where. Nothing here is aspirational.

Quick map of the moving parts:

| Piece | What | Runs where |
|---|---|---|
| **Mahsa** | Rust recomputation engine (`dif/`) — every ✓ Verified figure is its recomputation (§0.4) | sidecar binary / `dif` docker service |
| **API** | FastAPI app (`api/app/main.py:app`) — HTMX UI + `/api/*` JSON for the SPA | uvicorn :8000 / `api` docker service |
| **Scheduler** | `python -m app.jobs serve` — daily snapshot + 8pm CFO brief | `scheduler` docker service or cron |
| **Database** | SQLite (single-VPS) **or** Postgres/Supabase `tenant_core` schema + RLS (multi-tenant) | Supabase / any Postgres |
| **Better Auth** | TypeScript auth layer — issues the JWTs the API verifies | **OWNER-STEP** (you deploy it) |
| **Frontend SPA** | React/Vite (`frontend/`) — builds to static `dist/` | any static host |
| **Caddy** | TLS + reverse proxy (single-VPS stack only) | `caddy` docker service |

Env-var reference: `/.env.example` (master, every variable + purpose). Copy `api/.env.example`
→ `infra/.env` (docker stack) or `api/.env` (bare dev). Before anything else:

```bash
scripts/preflight.sh infra/.env     # env completeness + DB reachability + Mahsa presence
```

---

## 0 · Host requirements (WS10.2 — CERT-In posture)

Two host-level settings on the VPS **before first deploy** (`infra/deploy.sh` checks both —
NTP is a hard stop, retention a loud warning):

**NTP sync** — audit-chain and incident timestamps are evidence; CERT-In requires synchronised
clocks. Containers use the host clock, so this is host-level:

```bash
sudo timedatectl set-ntp true
timedatectl show -p NTPSynchronized --value   # must print: yes
```

Non-systemd host synced another way (chrony etc.): verify it, then `SKIP_NTP_CHECK=1 ./deploy.sh`.

**180-day log retention** — `docker-compose.prod.yml` sends every service's logs to the host
journal (journald driver; `docker logs` still works). The 180-day window is set host-side:

```bash
sudo install -D -m 0644 infra/host/journald-maisha.conf /etc/systemd/journald.conf.d/maisha.conf
sudo systemctl restart systemd-journald
journalctl -u systemd-journald --no-pager | tail -1   # sanity: journald restarted cleanly
```

`infra/host/journald-maisha.conf` sets `MaxRetentionSec=180day` (the time floor) and
`SystemMaxUse=4G` — if the journal nears 4G before 180 days pass, grow the cap and the disk;
never shrink the window below 180 days. Read back service logs with
`journalctl -t 'maisha/<container-name>'`.

---

## 1 · Provision the database

Two supported shapes. Pick one.

### 1a. SQLite (single-VPS, the docker-compose.prod.yml default)

Nothing to provision. The `migrate` compose service runs `alembic upgrade head` against
`sqlite:////data/maisha.db` on the `maisha_data` volume before the api starts
(`depends_on: service_completed_successfully`). Skip to §2.

### 1b. Postgres / Supabase (the multi-tenant launch path)

**OWNER-STEP** — create the project/instance:
- Supabase: create a project at supabase.com → Settings → Database → copy the **session-mode**
  connection string (direct port **5432** or the *session* pooler). **Do not use the
  transaction pooler (port 6543)**: RLS org isolation is bound via a session GUC
  (`app/core/principal.py` — `set_config('app.current_org', %s, false)`, re-issued on every
  SQLAlchemy pool checkout); transaction pooling reassigns server connections mid-session and
  breaks that binding. `scripts/preflight.sh` warns if it sees `:6543`.

**Apply the schema — `alembic upgrade head` is the authoritative path:**

```bash
cd api && source .venv/bin/activate        # or: make venv first
pip install -e ".[pg]"                     # psycopg2 driver (api/pyproject.toml [pg] extra)
# Admin URL for migrations (creates schema/roles; Supabase's postgres user works):
export MAISHA_DATABASE_URL='postgresql://postgres:PASSWORD@HOST:5432/postgres'
alembic upgrade head
```

Verified relationship between the two schema sources (read both before writing this):
`infra/db/multitenant/*.sql` (001–009) are the **reviewable source** and the input to the CI
gates (`scripts/check_rls_coverage.sh`, `scripts/rls_redteam.sh`). The Alembic revisions inline
that SQL **verbatim** as immutable snapshots (`0002` = 001_tenancy + 002_domain_rls +
003_identity; `0004` = 004_legal; `0006` = 005_ca_threads; `0007` = 006_ca_seat; `0008` =
007_job_runs; `0010` = 008_dpdp; `0011` = 009_org_memory — each states this in its docstring). **Never apply the `.sql` files directly to
production**; `alembic upgrade head` is the one path, and it also stamps the version table so
future upgrades work.

What the migration creates: the **`tenant_core` schema** (multi-tenant tables; the old
single-tenant tables stay in `public` per 0002's docstring), the **`maisha_app` NOLOGIN role**
(RLS applies to it; grants are issued to it), `app_current_org()` and every table's RLS policy
(ENABLE + FORCE) in the same revision (§0.8).

**OWNER-STEP — create the app's login user** (the migration deliberately creates only the
NOLOGIN role; connect as admin and run):

```sql
CREATE ROLE maisha_svc LOGIN PASSWORD '<strong-password>' IN ROLE maisha_app;
GRANT USAGE ON SCHEMA tenant_core TO maisha_app;
```

The `GRANT USAGE` line is required: the migrations grant table privileges to `maisha_app` but no
migration grants schema usage on `tenant_core` (verified — no `GRANT USAGE` exists in
`api/alembic/versions/` or `infra/db/multitenant/`), and without it every query fails with
"permission denied for schema". `maisha_svc` inherits `maisha_app`'s table grants and, being a
non-superuser, is subject to the FORCEd RLS.

**The app's runtime URL** (goes in `.env` as `MAISHA_DATABASE_URL` — note the app user, not
postgres, and the search_path, exactly as `app/jobs.py` documents):

```
postgresql://maisha_svc:PASSWORD@HOST:5432/postgres?options=-csearch_path%3Dtenant_core,public
```

**Verify RLS actually holds (red-team, live):**

```bash
# Point PG_PSQL at a Postgres where you can create/drop a scratch DB (needs CREATEDB).
# It creates+drops `ws4_rls_test` — NEVER point it at the production database/Supabase prod.
PG_PSQL="psql -U postgres -h 127.0.0.1" scripts/rls_redteam.sh
```

This applies 001+002 to a throwaway DB and proves, as a non-superuser, that org A cannot
read/write/update org B's rows and that an unbound session matches zero rows (fail-closed).
`make ci` runs the same script; in CI a skip is a failure.

**Importing existing single-tenant data:** `app/db/importer.py` copies a pre-multi-tenancy
SQLite database into `tenant_core` with a checksum reconciliation report
(`api/tests/integration/test_import_roundtrip.py` is the proof; its Postgres leg runs when
`MAISHA_TEST_POSTGRES_URL` is set).

---

## 2 · Build and deploy Mahsa (the Rust engine)

```bash
cd dif && cargo build --release            # → dif/target/release/mahsa
```

Contract (verified in `dif/src/main.rs` + `api/tests/conftest.py`):
- Listens on `MAHSA_ADDR` (default `0.0.0.0:8088`); endpoints `GET /health`, `POST /fold`.
- Rules are **embedded in the binary** (tested set). `MAHSA_RULES=/path/rules.yaml` overrides —
  leave unset unless you know why. Setting it also **requires** `MAHSA_RULES_MANIFEST=/path/
  MANIFEST.yaml` (version + sha256): a file pack loads only with a verified manifest, else Mahsa
  refuses to boot (WS1.E3 — see `docs/RULE_PACK_SLA.md`).
- The API reaches it at `MAISHA_MAHSA_URL` (default `http://127.0.0.1:8088`; in docker
  `http://dif:8088` — compose sets this).
- The test suite expects the binary at `dif/target/{debug,release}/mahsa` (conftest skips
  integration tests without it; `make ci` builds it first so nothing can silently skip).

In the docker stacks Mahsa is the `dif` service (multi-stage build, its own image) — nothing to
do beyond `docker compose build`. If Mahsa is down at runtime the API degrades honestly
(◐ honest-pending / explicit banner), it never fabricates a ✓.

---

## 3 · Deploy the API + scheduler

### 3a. Docker (single VPS — the shipped path)

```bash
cd infra
cp ../api/.env.example .env                # then EDIT — preflight will tell you what's missing
../scripts/preflight.sh .env
./deploy.sh                                # build → migrate (one-shot) → up -d → health wait
```

`deploy.sh` (verified): refuses to run without `infra/.env`, warns if
`MAISHA_ENVIRONMENT` isn't `production`, runs the `migrate` service to completion, brings the
stack up, polls `GET /health` in the api container. Only Caddy publishes ports (80/443) and
auto-provisions TLS for `MAISHA_DOMAIN` (`infra/Caddyfile`). To use Postgres instead of the
on-volume SQLite, set `MAISHA_DATABASE_URL` in `infra/.env` — compose interpolates it into the
`migrate`/`api`/`scheduler` services (falls back to SQLite when unset).

Production boot behaviour (verified in `app/main.py` / `app/core/betterauth.py`): with
`MAISHA_ENVIRONMENT=production` the app **refuses to start** without `MAISHA_BETTER_AUTH_URL`
or with the default `MAISHA_SESSION_SECRET` (it signs action preview tokens). Every request
needs a Better Auth JWT (§4). Public paths are only `/health`, `/login`, `/static`. Schema is
NOT auto-created in production — migrations are the only path (`main.py` gates `create_all` on
non-production).

**ONE auth system (P2-6 — the legacy HMAC password login is DELETED).** HTMX pages and the SPA
share the same Better Auth JWT, verified through the same JWKS path
(`app/core/betterauth.py`): the SPA sends `Authorization: Bearer <jwt>`; the HTMX surface
carries the SAME JWT in the `maisha_jwt` cookie (a present bearer header always wins — a bad
header token is rejected, never replaced by the cookie). `GET /login` is now only a redirect to
the sign-in page (`MAISHA_SIGNIN_URL`, default `/sign-in`, the SPA route); `POST /logout` just
drops the cookie. **OWNER-STEP:** after Better Auth sign-in, your frontend/TS layer must place
the JWT (from `GET {BETTER_AUTH_URL}/api/auth/token`) in the `maisha_jwt` cookie for the API's
origin — until it does, the HTMX pages redirect to sign-in and only the SPA (bearer header) is
usable. There is no password fallback, deliberately.

### 3b. Bare uvicorn (if you skip docker)

```bash
make venv && cd api && source .venv/bin/activate
pip install -e ".[ocr,pg]"                 # ocr optional (needs system tesseract-ocr); pg for Postgres
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 4 · Better Auth (the TS auth layer) — OWNER-STEP

The repo does **not** contain a Better Auth server; you deploy one (Node; better-auth.com) and
the API only verifies its JWTs via JWKS (`app/core/betterauth.py`: algorithms pinned to
EdDSA/ES256/RS256, exp+iss+aud required, org from the `activeOrganizationId` claim only,
fail-closed everywhere).

What you must configure on YOUR Better Auth server (verified against
`frontend/src/lib/auth.ts`, which documents this verbatim — the default JWT payload does NOT
carry these claims and the API denies without them):

```ts
betterAuth({
  plugins: [
    organization(),
    twoFactor(),
    jwt({ jwt: { definePayload: async ({ user, session }) => ({
      sub: user.id,
      email: user.email,                                   // absent ⇒ 401
      activeOrganizationId: session.activeOrganizationId,  // absent ⇒ 403
      role: /* caller's role in that org (member row) */,  // absent/unmapped ⇒ 403
      // optional: the MFA claim named by MAISHA_BETTER_AUTH_MFA_CLAIM
      // optional: the plan claim named by MAISHA_BETTER_AUTH_PLAN_CLAIM (default "plan")
    }) } }),
  ],
})
```

Then set, on the API side (`.env`):

| Var | Value |
|---|---|
| `MAISHA_BETTER_AUTH_URL` | your Better Auth base URL (JWKS is fetched from `{URL}/api/auth/jwks`) |
| `MAISHA_BETTER_AUTH_ISSUER` / `_AUDIENCE` | only if you changed them from Better Auth's default (= base URL) |
| `MAISHA_BETTER_AUTH_MFA_CLAIM` | only once the claim above is actually emitted — set it earlier and every request is denied |

And on the frontend build: `VITE_BETTER_AUTH_URL` (the SPA signs in against it and fetches its
JWT from `GET {URL}/api/auth/token`, session cookie attached).

Role mapping (verified `app/core/principal.py`): `owner→OWNER, admin→ADMIN,
member→ACCOUNTANT, approver→APPROVER`, unknown → denied.

---

## 5 · Frontend (React SPA)

```bash
cd frontend
cp .env.example .env.production            # set VITE_API_BASE + VITE_BETTER_AUTH_URL
npm ci && npm run build                    # → frontend/dist/ (static; includes PWA sw.js/manifest)
```

Vite bakes the two vars in at build time — changing them means rebuilding.

**Launch-day reality check (verified, not aspirational):** the API has **no CORS middleware**
(grep `CORSMiddleware`/`cors` across `api/app` — zero hits), so a browser on a *different
origin* cannot call `/api/*` — the SPA's `Authorization` header triggers a CORS preflight the
API never answers. And serving the SPA on the *same* origin collides with the HTMX app: both
own `/today`, `/inbox`, … (`app/main.py` routes vs `frontend/src/App.tsx`). Therefore:

- **Launch surface today = the HTMX web app** (Today, hubs, Exception Inbox, Audit Room, audit
  pack downloads) — served by the API itself, nothing extra to host, full verification-badge
  honesty. This is the zero-extra-work path.
- **Hosting the React SPA** (e.g. Vercel — project root `frontend`, build `npm run build`,
  output `dist`, the two env vars in the dashboard) additionally requires adding
  CORS middleware to the API with your SPA origin allow-listed — a small, deliberate backend
  change that touches the auth surface of every route, so it is **flagged as a follow-up code
  ticket, not smuggled into this launch pack**. Better Auth handles its own CORS via its
  `trustedOrigins` config (**OWNER-STEP** on that server if you deploy the SPA).

---

## 6 · Scheduled jobs (cron)

One CLI, verified in `app/jobs.py`:
`python -m app.jobs {capture|brief|dunning|alerts|evolve|audit-verify|all|serve}` — each runs
once and exits (exit 0 = no job errored; idempotent same-period re-runs are no-ops via the
`job_run` ledger, migration 0008), `serve` is the long-lived loop the docker `scheduler`
service runs (fires at `MAISHA_BRIEF_HOUR`:`MAISHA_BRIEF_MINUTE` `MAISHA_BRIEF_TZ`, default
20:00 IST). `evolve` is the nightly company-memory evolution (MEM.P1-1: deterministic
re-consolidation + bounded history prune, audit-sealed); it is part of `all`, so the cron
line below already runs it nightly.

Docker stack: nothing to do — the `scheduler` service is included. External cron instead
(from the module's own docstring):

```cron
# m h dom mon dow
0 20 * * *  cd /srv/maisha && api/.venv/bin/python -m app.jobs all
```

Env needed by the job run: `MAISHA_DATABASE_URL` (on Postgres, the §1b URL with search_path),
`MAISHA_MAHSA_URL` (for `brief`), `MAISHA_CFO_EMAIL`/`MAISHA_SMTP_*`/`MAISHA_EMAIL_SENDER`
(for `brief`/`dunning`/`alerts`). Jobs iterate all orgs with per-tenant failure isolation.

**OWNER-STEP (SMTP):** any authenticated relay — set `MAISHA_SMTP_HOST/PORT/USERNAME/PASSWORD`,
`MAISHA_SMTP_USE_TLS=true` for TLS ports.

---

## 7 · Backups (single-VPS/SQLite path)

`infra/backup/backup.sh` — restic, consistent SQLite snapshot via the online-backup API.
**OWNER-STEP:** create `/etc/maisha/backup.env` with `RESTIC_REPOSITORY` + `RESTIC_PASSWORD`,
install `infra/backup/restic.cron` into `/etc/cron.d/`. Restore drill: `infra/backup/restore.sh`
(restores to `./restore-out`, never the live volume). On Supabase, use its built-in PITR/backups
instead (**OWNER-STEP**: enable in dashboard).

---

## 8 · Post-deploy smoke (all three must pass)

```bash
# 1. The full gate — 19 steps: cargo build/test/clippy, ruff, mypy, 4 grep-gates, unit,
#    integration, oracle gaps-vs-regressions, E2E real loop, live RLS red-team, golden eval,
#    npm ci, tsc, vitest, oxlint (scripts/ci_gate.sh — same file CI runs, verbatim).
make ci

# 2. Live tenant isolation against a real Postgres (see §1b; scratch server, never prod):
PG_PSQL="psql -U postgres -h 127.0.0.1" scripts/rls_redteam.sh

# 3. One end-to-end VERIFIED figure — the real API + real Mahsa binary computing a figure,
#    claiming it, and Mahsa recomputing it to the paisa (a ₹-tampered claim must block):
cd api && .venv/bin/pytest tests/integration/test_verified_flow.py -q
```

Then against the running deployment:

```bash
curl -sf https://<your-domain>/health          # api up (public route)
curl -sf https://<your-domain>/audit/verify    # audit hash-chain intact (route in app/main.py)
```

and in the browser: sign in via Better Auth, open **Today** — the runway figure must show the
✓/◐ verification chip with a working panel (inputs → formula → verdict hash). A ✓ there means
Mahsa recomputed that number this session; ◐ means honest-pending — both are correct states,
a missing chip is not.

---

## 9 · OWNER-STEP summary (external accounts — nothing else is blocked on you)

| Step | Where | What to enter |
|---|---|---|
| Supabase/Postgres project | supabase.com | session-mode URL → §1b; run the two-line SQL (login role + schema grant) |
| Better Auth deployment | your Node host | plugins + `definePayload` from §4; its URL → `MAISHA_BETTER_AUTH_URL` + `VITE_BETTER_AUTH_URL` |
| Domain + DNS | your registrar | A record → VPS; name → `MAISHA_DOMAIN` (Caddy does TLS) |
| SMTP relay | any provider | creds → `MAISHA_SMTP_*` |
| Static host for SPA | e.g. Vercel | build config + 2 env vars from §5 |
| Backups | S3/anywhere restic speaks | `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` → §7 |
| Anthropic API key (optional, only if `MAISHA_LLM_PROVIDER=claude`) | console.anthropic.com | → `MAISHA_CLAUDE_API_KEY` |
| Alert webhook (WS10.2) | any webhook receiver (Slack/Discord/alertmanager) | → `MAISHA_ALERT_WEBHOOK_URL` — see §10 |
| Razorpay | — | **nothing to configure — no billing integration exists in the code yet (WS6.4 unbuilt)** |

---

## 10 · Incident alerting (WS10.2 — CERT-In posture)

Severity events (today: every unhandled 5xx, via `app/core/alerting.py` wired in
`app.main._unhandled_error`) are logged at ERROR always, and additionally POSTed as JSON
(`{source, event, severity, detail, at}` — no PII) to `MAISHA_ALERT_WEBHOOK_URL` when set.

**OWNER-STEP:** point `MAISHA_ALERT_WEBHOOK_URL` at a webhook a human actually sees
(Slack/Discord incoming webhook, or an alertmanager receiver). Unset = local log only — fine in
dev, not in production: CERT-In's 6-hour reporting clock runs from *noticing* the incident, so
noticing must be push, not log-grepping. When an alert fires and looks like a reportable
incident, follow `docs/legal/CERTIN_INCIDENT_REPORT_TEMPLATE.md` (which references the
personal-data-breach runbook where both apply).
