-- MMX-1.0 §WS10.4 — legal kit: append-only acceptance log.
--
-- TENANT-SCOPED. An acceptance is a fact about a customer org (its user bound the org to a
-- ToS/Privacy/DPA version), so the row carries org_id and gets the standard RLS treatment used
-- by every other tenant-scoped table in 001/002/003: policy keyed on app_current_org(), which
-- reads the session GUC the app sets from the VERIFIED JWT claim — never a request body (§0.8).
-- With no org bound, app_current_org() is NULL and this policy matches zero rows (fail closed).
--
-- There is deliberately NO legal_document table: the set of published versions points at files
-- in docs/legal/ that only a deploy can change, so it lives in code (app.core.legal.PUBLISHED),
-- not in the tenant schema. See that module's docstring.
--
-- Append-only is enforced by the GRANT, not by convention: the app role gets SELECT and INSERT
-- and is never granted UPDATE or DELETE, so the evidence cannot be rewritten by the application
-- even with a bug or an injected statement. Corrections are new rows.

CREATE TABLE legal_acceptance (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id      uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  doc_type     text NOT NULL CHECK (doc_type IN ('tos', 'privacy', 'dpa')),
  version      text NOT NULL,
  accepted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX legal_acceptance_lookup ON legal_acceptance(org_id, user_id, doc_type);

ALTER TABLE legal_acceptance ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_acceptance FORCE  ROW LEVEL SECURITY;
CREATE POLICY legal_acceptance_tenant ON legal_acceptance
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON legal_acceptance TO maisha_app;
