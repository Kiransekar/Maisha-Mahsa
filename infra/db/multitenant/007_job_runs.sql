-- MMX-1.0 §WS4.5 — scheduled-job idempotency ledger: one row per (org, job, period).
-- A job re-run for a period it already completed ('done') is a no-op; an 'error' row does
-- NOT block a retry. Tenant-scoped, so it ships with its RLS policy here (§0.8).

CREATE TABLE job_run (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id   uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  job      text NOT NULL,
  period   text NOT NULL,             -- ISO date the run covered
  status   text NOT NULL CHECK (status IN ('done', 'error')),
  ran_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, job, period)
);

ALTER TABLE job_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_run FORCE  ROW LEVEL SECURITY;
CREATE POLICY job_run_tenant ON job_run
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE ON job_run TO maisha_app;
