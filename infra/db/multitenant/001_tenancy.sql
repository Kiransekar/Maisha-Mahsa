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
