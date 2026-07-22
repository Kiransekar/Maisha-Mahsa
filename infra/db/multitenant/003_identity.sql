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
