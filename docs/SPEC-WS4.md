# SPEC-WS4 — Multi-tenant platform schema & RLS (MMX-1.0 §WS4.1)

The target schema for the P1 platform. Per §WS4.1 this **precedes all P1 code** — every domain
table migrated in WS4.2 conforms to the tenancy + RLS pattern fixed here. Authority is
`docs/MASTER_PLAN.md`; this is a design note.

## Tenancy model
`org → entity → gstin_registration → domain rows`.

- **org** — the tenant boundary. Everything a customer owns lives under one org; nothing crosses
  org lines except through privileged provisioning.
- **entity** — a legal entity within the org (a company/LLP). Books, payroll, journals scope here.
- **gstin_registration** — a GST registration under an entity. Ledgers, ITC and GST returns are
  scoped to a registration (G6 multi-GSTIN): an org with two GSTINs keeps their ITC/returns apart.
- **app_users / memberships** — users are global identities; a membership binds a user to an org
  with a role (drives RBAC in WS5 and the org claim in the JWT).

## The security invariant (§0.8)
Every tenant-scoped table carries `org_id NOT NULL` and is protected by **row-level security**
keyed on the **session's org**, never a request-body value:

```sql
CREATE POLICY <t>_tenant ON <t>
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE  ROW LEVEL SECURITY;   -- applies even to the table owner
```

- `app_current_org()` reads `current_setting('app.current_org')`, which the app sets **once per
  request from the verified JWT claim** (in Supabase, `auth.jwt()->>'org_id'`). No SQL ever takes
  org from user input. Unset → `NULL` → the policy matches no rows (**fail-closed**).
- The application connects as the **non-superuser** role `maisha_app`, so RLS applies. Migrations
  and admin run as the owner/superuser, which bypasses RLS by design — the only path that writes
  rows across org lines (provisioning).
- `WITH CHECK` blocks writing a row tagged for another org; `FORCE` closes the owner-bypass hole.

## Money & ids
BIGINT paise for all money (matches the SQLite `INTEGER paise` deviation, widened for Postgres).
`uuid` primary keys (`gen_random_uuid()`), Supabase-native.

## Storage prefix scheme
Object storage is partitioned by tenant: `org/<org_id>/entity/<entity_id>/…`. Signed-URL issuance
checks the caller's org claim against the prefix; the tenancy red-team (WS4.7) probes storage
paths too.

## What is proven here (WS4.1)
- `infra/db/multitenant/001_tenancy.sql` — tenancy core (orgs, entities, gstin_registrations,
  app_users, memberships) + `app_current_org()` + RLS + the `maisha_app` role.
- `infra/db/multitenant/002_domain_rls.sql` — the RLS pattern applied to representative
  money-critical domain tables (bills, invoices, journal_entries, gst_returns).
- `scripts/check_rls_coverage.sh` — CI gate (wired into `make gates`): every tenant table ships
  RLS + a policy or the build fails (§0.8). Proven to catch a leaky table.
- `scripts/rls_redteam.sh` + `rls_redteam.sql` — a **live** proof against Postgres: an org-A
  session cannot read, write, or update org-B rows, and an unbound session sees nothing. PASSED.

## Roadmap (subsequent WS4 tickets)
- **WS4.2** migration engineering: replay all 36 SQLite tables to Postgres with org_id + RLS
  (each migration ships its policy or CI fails); SQLite tenant importer with a checksum
  reconciliation report.
- **WS4.3** auth: Supabase Auth (OTP/Google), MFA for Owner/Admin/Approver; delete the
  HMAC-cookie system. *(Supabase provisioning = Human, §0.7.)*
- **WS4.4** per-tenant hash-chain genesis + daily anchored chain-root + `/audit/verify` per tenant.
- **WS4.5** scheduled jobs tenant-iterated with per-tenant failure isolation.
- **WS4.6** promote api-nest to the main line; Python retained as a CI oracle cross-check.
- **WS4.7** tenancy red-team suite in CI over every route and storage path (this SQL red-team is
  its seed).
- **WS4.8** CI/CD assembly (full gate blocking main).

**Human-gated (§0.7):** Supabase/Vercel accounts, provisioning, and billing.
