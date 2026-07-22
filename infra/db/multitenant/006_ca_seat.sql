-- MMX-1.0 §WS8.3 — CA seat onboarding: an invite is a membership PENDING acceptance.
-- No new identity tables (no parallel auth): `memberships` (001_tenancy.sql) gains a status.
-- Pre-existing rows are real members -> 'active'. The RLS policy from 001 covers the new
-- column automatically (row-level, not column-level).

ALTER TABLE memberships
  ADD COLUMN status text NOT NULL DEFAULT 'active' CHECK (status IN ('pending', 'active'));
