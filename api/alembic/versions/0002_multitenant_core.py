"""multi-tenant core replay — tenancy schema + RLS policies onto Postgres (WS4.2)

Creates the ``tenant_core`` schema and, inside it, the multi-tenant tenancy core, the
tenant-scoped domain tables, and the identity tables — each with its row-level-security policy
in this same migration (§0.8).

The SQL below is INLINED, not read from disk. A migration's content must be immutable: its
identity is its revision id, Alembic runs it exactly once, and a database already at
``0002_multitenant_core`` will never re-run it. An earlier version of this file resolved its
content at runtime with ``sorted(Path(...).glob("[0-9][0-9][0-9]_*.sql"))``, which meant editing
or adding a file under ``infra/db/multitenant/`` silently changed what this revision "was" —
so two databases both reporting revision ``0002_multitenant_core`` could hold different schemas,
and a table added to that directory would reach fresh databases while never reaching existing
ones. The blocks below are a verbatim snapshot of ``001_tenancy.sql``, ``002_domain_rls.sql`` and
``003_identity.sql`` as of this revision. Those files remain the reviewable/red-team source and
the input to ``scripts/check_rls_coverage.sh``; any LATER schema change is a NEW revision, never
an edit to this one.

ponytail: a dedicated schema — not ``public`` — is the smallest change that avoids colliding
with the single-tenant app tables ``0001_baseline`` still owns in ``public`` (same table names:
``documents``, ``employees``, ``vendors``, ... with different, pre-multi-tenancy column shapes).
Editing ``0001_baseline`` or the ORM models to retire those tables is a WS4.6 backend-promotion
concern; this migration only adds the new target schema alongside the old one.
``api/app/db/importer.py`` reads/writes ``tenant_core`` explicitly.

No-ops on SQLite (dev/test): RLS, ``CREATE ROLE``, and ``gen_random_uuid()`` are Postgres-only.

Revision ID: 0002_multitenant_core
Revises: 0001_baseline
Create Date: 2026-07-21
"""

# ruff: noqa: E501 — the SQL below is a verbatim snapshot; reflowing it would break the
# byte-for-byte correspondence with infra/db/multitenant/*.sql that makes it reviewable.
from __future__ import annotations

from alembic import op

revision = "0002_multitenant_core"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


# ---- snapshot of infra/db/multitenant/001_tenancy.sql -----------------------------------
_001_SQL = """
-- MMX-1.0 §WS4.1 — multi-tenant target schema (tenancy core + RLS).
-- The tenant boundary is org → entity → gstin_registration → domain tables. Every tenant-scoped
-- table carries org_id and is protected by row-level security keyed on the SESSION's org — never
-- a value from a request body (§0.8). The app connects as a NON-superuser role so RLS applies;
-- migrations/admin run as the owner/superuser (which bypasses RLS by design). BIGINT paise.
--
-- The current org is read from a session GUC the app sets from the VERIFIED JWT claim
-- (org_id from session context, §0.8). In Supabase this maps to auth.jwt()->>'org_id'; here we
-- use current_setting('app.current_org') so the policies are testable with plain Postgres.

-- ---- application role (RLS applies to it; NOT a superuser) -----------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'maisha_app') THEN
    CREATE ROLE maisha_app NOLOGIN;
  END IF;
END $$;

-- ---- session → org resolver -----------------------------------------------------------
-- Returns the org bound to this session, or NULL when unset (RLS then matches no rows —
-- fail-closed, never leak across tenants).
CREATE OR REPLACE FUNCTION app_current_org() RETURNS uuid
  LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.current_org', true), '')::uuid
$$;

-- ---- tenancy roots --------------------------------------------------------------------
CREATE TABLE orgs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  plan        text NOT NULL DEFAULT 'basics',   -- entitlement tier (WS6)
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entities (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  legal_name  text NOT NULL,
  pan         text,
  state_code  text,                              -- for state packs (WS2)
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entities_org ON entities(org_id);

-- Multi-GSTIN scoping (G6): ledgers/ITC/returns are scoped to a specific registration.
CREATE TABLE gstin_registrations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  gstin       text NOT NULL,
  state_code  text NOT NULL,
  filing_profile text NOT NULL DEFAULT 'monthly',   -- monthly | qrmp | composition (WS1.D2)
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, gstin)
);
CREATE INDEX gstin_registrations_org ON gstin_registrations(org_id);

-- Users are global identities; membership binds a user to an org with a role (RBAC, WS5).
CREATE TABLE app_users (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  role        text NOT NULL,                     -- owner|admin|accountant|approver|ca|investor
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, user_id)
);
CREATE INDEX memberships_org ON memberships(org_id);

-- RLS on the tenancy tables themselves (orgs is filtered to the current org; the rest by org_id).
ALTER TABLE orgs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE orgs                FORCE  ROW LEVEL SECURITY;
CREATE POLICY orgs_tenant ON orgs
  USING (id = app_current_org()) WITH CHECK (id = app_current_org());

ALTER TABLE entities            ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities            FORCE  ROW LEVEL SECURITY;
CREATE POLICY entities_tenant ON entities
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE gstin_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE gstin_registrations FORCE  ROW LEVEL SECURITY;
CREATE POLICY gstin_registrations_tenant ON gstin_registrations
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE memberships         ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships         FORCE  ROW LEVEL SECURITY;
CREATE POLICY memberships_tenant ON memberships
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE, DELETE ON orgs, entities, gstin_registrations, app_users, memberships TO maisha_app;
"""


# ---- snapshot of infra/db/multitenant/002_domain_rls.sql --------------------------------
_002_SQL = """
-- MMX-1.0 §WS4.1 — domain tables, tenant-scoped. This file demonstrates the RLS pattern EVERY
-- domain table follows; the full 36-table replay from SQLite is WS4.2 migration engineering, and
-- each migrated table ships its org_id + RLS in the same migration or CI fails (§0.8,
-- scripts/check_rls_coverage.sh). Money is BIGINT paise. Reg-scoped tables (GST) also carry
-- gstin_registration_id (G6). Included here (WS4.7 widened the sample to the money/PII-bearing
-- tables the red-team targets): bills, invoices, journal_entries, gst_returns, vendors, customers,
-- bank_accounts, employees, tds_returns, documents.

CREATE TABLE bills (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  vendor_id   uuid,
  bill_number text NOT NULL,
  bill_date   date NOT NULL,
  subtotal    bigint NOT NULL,        -- paise (taxable value)
  tds_amount  bigint NOT NULL DEFAULT 0,
  total_amount bigint NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bills_org ON bills(org_id);

CREATE TABLE invoices (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  gstin_registration_id uuid REFERENCES gstin_registrations(id) ON DELETE SET NULL,
  invoice_number text NOT NULL,
  invoice_date date NOT NULL,
  taxable_value bigint NOT NULL,      -- paise
  total_tax   bigint NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invoices_org ON invoices(org_id);

CREATE TABLE journal_entries (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  entry_date  date NOT NULL,
  narration   text,
  amount      bigint NOT NULL,        -- paise
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX journal_entries_org ON journal_entries(org_id);

CREATE TABLE gst_returns (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  gstin_registration_id uuid NOT NULL REFERENCES gstin_registrations(id) ON DELETE CASCADE,
  return_type text NOT NULL,
  filing_period text NOT NULL,
  tax_payable bigint NOT NULL DEFAULT 0,  -- paise (cash)
  late_fee    bigint NOT NULL DEFAULT 0,
  interest    bigint NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX gst_returns_org ON gst_returns(org_id);

-- ---- money/PII-bearing domain tables (WS4.7 red-team targets) --------------------------
-- vendors / customers carry PAN + GSTIN (PII); same tenant-scoped pattern.
CREATE TABLE vendors (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name        text NOT NULL,
  pan         text,                    -- PII
  gstin       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vendors_org ON vendors(org_id);

CREATE TABLE customers (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name        text NOT NULL,
  pan         text,                    -- PII
  gstin       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX customers_org ON customers(org_id);

-- bank_accounts: account number + IFSC are PII; balance is money (paise).
CREATE TABLE bank_accounts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id      uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  account_number text NOT NULL,        -- PII
  ifsc           text NOT NULL,
  balance        bigint NOT NULL DEFAULT 0,   -- paise
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bank_accounts_org ON bank_accounts(org_id);

-- employees: PAN/UAN + salary are PII/money.
CREATE TABLE employees (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name         text NOT NULL,          -- PII
  pan          text,                   -- PII
  uan          text,                   -- PII
  gross_salary bigint NOT NULL DEFAULT 0,   -- paise
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX employees_org ON employees(org_id);

-- tds_returns: reg-scoped statutory return (deductor-side).
CREATE TABLE tds_returns (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  form_type   text NOT NULL,           -- 24Q/26Q/27Q (regime-aware, WS1.A)
  quarter     text NOT NULL,           -- e.g. 2026-Q1
  total_tds   bigint NOT NULL DEFAULT 0,   -- paise
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tds_returns_org ON tds_returns(org_id);

-- documents: the DB-side of object-storage tenancy. storage_prefix is the tenant-scoped path
-- (e.g. 'org/<org_id>/...') that WS4.1 isolates in the bucket; RLS here proves org A can never
-- reach a row — hence a storage_prefix — that belongs to org B (real bucket ACL red-teaming is
-- WS4.2/WS4.3, see rls_redteam.sql header).
CREATE TABLE documents (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id      uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  doc_type       text NOT NULL,
  storage_prefix text NOT NULL,        -- tenant-scoped object-storage path
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_org ON documents(org_id);

-- ---- RLS: org_id = the session org, on every table (§0.8) -----------------------------
ALTER TABLE bills            ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills            FORCE  ROW LEVEL SECURITY;
CREATE POLICY bills_tenant ON bills
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE invoices         ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices         FORCE  ROW LEVEL SECURITY;
CREATE POLICY invoices_tenant ON invoices
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE journal_entries  ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entries  FORCE  ROW LEVEL SECURITY;
CREATE POLICY journal_entries_tenant ON journal_entries
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE gst_returns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gst_returns      FORCE  ROW LEVEL SECURITY;
CREATE POLICY gst_returns_tenant ON gst_returns
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE vendors          ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendors          FORCE  ROW LEVEL SECURITY;
CREATE POLICY vendors_tenant ON vendors
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE customers        ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers        FORCE  ROW LEVEL SECURITY;
CREATE POLICY customers_tenant ON customers
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE bank_accounts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts    FORCE  ROW LEVEL SECURITY;
CREATE POLICY bank_accounts_tenant ON bank_accounts
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE employees        ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees        FORCE  ROW LEVEL SECURITY;
CREATE POLICY employees_tenant ON employees
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE tds_returns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tds_returns      FORCE  ROW LEVEL SECURITY;
CREATE POLICY tds_returns_tenant ON tds_returns
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE documents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents        FORCE  ROW LEVEL SECURITY;
CREATE POLICY documents_tenant ON documents
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE, DELETE ON
  bills, invoices, journal_entries, gst_returns,
  vendors, customers, bank_accounts, employees, tds_returns, documents
  TO maisha_app;
"""


# ---- snapshot of infra/db/multitenant/003_identity.sql ----------------------------------
_003_SQL = """
-- MMX-1.0 §WS4.3 — identity layer: password credentials, sessions, MFA (TOTP) enrolment.
--
-- `app_users` and `memberships` already exist (001_tenancy.sql) and are NOT redefined here.
-- password_credentials / mfa_totp are per-user identity data, the same category as `app_users`
-- itself: a user's password or TOTP seed isn't scoped to a tenant (a user can hold memberships
-- in many orgs), so — matching the existing `app_users` precedent, which also carries no org_id
-- and no RLS policy — these two tables carry no org_id and no RLS policy either: there is no
-- tenant dimension to filter them by.
--
-- `sessions` IS tenant-scoped: a session is bound to one org context at issue time (§0.8 — the
-- app resolves org_id/role from THIS row + the matching membership, server-side, never from a
-- request body), so it gets the standard org_id + RLS treatment used by every other tenant-scoped
-- table in 001/002. Only the sha256 hash of the bearer token is stored; the raw token is returned
-- once, at issue time, and never persisted (so a DB read alone can never impersonate a session).

CREATE TABLE password_credentials (
  user_id        uuid PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  password_hash  text NOT NULL,       -- "scrypt$N$r$p$saltHex$hashHex" (stdlib hashlib.scrypt)
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mfa_totp (
  user_id     uuid PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  secret      text NOT NULL,          -- base32 TOTP seed (RFC 6238)
  verified    boolean NOT NULL DEFAULT false,
  enrolled_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash  text NOT NULL UNIQUE,   -- sha256(raw bearer token); raw token is never persisted
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz
);
CREATE INDEX sessions_org  ON sessions(org_id);
CREATE INDEX sessions_user ON sessions(user_id);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE  ROW LEVEL SECURITY;
CREATE POLICY sessions_tenant ON sessions
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE, DELETE ON password_credentials, mfa_totp, sessions TO maisha_app;
"""

# In dependency order: tenancy roots (orgs/entities/gstin_registrations/app_users) must exist
# before the domain tables and the identity tables that reference them.
SCHEMA_SQL: tuple[str, ...] = (_001_SQL, _002_SQL, _003_SQL)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # ponytail: sqlite dev/test has no RLS/roles/uuid-gen — nothing to replay
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {TENANT_SCHEMA}")
    op.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
    for stmt in SCHEMA_SQL:
        op.execute(stmt)
    op.execute("SET search_path TO public")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"DROP SCHEMA IF EXISTS {TENANT_SCHEMA} CASCADE")
