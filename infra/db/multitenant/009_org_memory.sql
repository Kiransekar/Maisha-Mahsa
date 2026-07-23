-- SPEC-MEMCITE-1.0 §A2 (MEM.P0-1) — per-company memory layer: the CFO posture block
-- (org_memory), its non-destructive version trail (org_memory_history, survey §5.2.2
-- soft/temporal updates — archive-on-supersede, never overwrite), and playbook adopt/dismiss
-- feedback (experiential memory; dismissed moves stop counting toward quantified savings).
--
-- TENANT-SCOPED (§0.8). org_id is uuid keyed to orgs(id) — fixes api-nest defect (c)
-- (integer company_id default 1) — and every table gets the standard RLS treatment used by
-- 001–008: policy keyed on app_current_org(), the session GUC the app sets from the VERIFIED
-- JWT claim, never a request body. No org bound -> NULL -> zero rows (fail closed).
--
-- The 2200-char cap on the posture block is DB-enforced (§0.8 spirit): reject-on-overflow is
-- the app contract (never silent truncation, §0.4 culture), and the CHECK makes an app bug
-- unable to smuggle an oversized block past it. The cap doubles as the importance-based
-- forgetting pressure (survey §5.2.3).
--
-- Grants are least-privilege, per table:
--   org_memory          S/I/U  — the block is replaced (archive-on-supersede), never deleted.
--   org_memory_history  S/I/D  — DELETE is for the nightly evolve() job's BOUNDED archival
--                                prune (MEM.P1-1); active memory is never deleted.
--   playbook_feedback   S/I/U  — latest verdict wins via upsert.

CREATE TABLE org_memory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  kind        text NOT NULL DEFAULT 'cfo_posture',      -- one kind today; text not enum
  content     text NOT NULL CHECK (char_length(content) <= 2200),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  updated_by  text NOT NULL,                            -- Principal.user_id
  UNIQUE (org_id, kind)
);
CREATE INDEX org_memory_org ON org_memory(org_id);

CREATE TABLE org_memory_history (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  kind          text NOT NULL,
  content       text NOT NULL,
  superseded_at timestamptz NOT NULL DEFAULT now(),
  superseded_by text NOT NULL,
  audit_seq     bigint                                  -- row id of the sealed memory.update event
);
CREATE INDEX org_memory_history_org ON org_memory_history(org_id, kind);

CREATE TABLE playbook_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  playbook_id text NOT NULL,
  verdict     text NOT NULL CHECK (verdict IN ('adopted', 'dismissed')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  created_by  text NOT NULL,
  UNIQUE (org_id, playbook_id)                          -- latest verdict wins via upsert
);
CREATE INDEX playbook_feedback_org ON playbook_feedback(org_id);

ALTER TABLE org_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_memory FORCE  ROW LEVEL SECURITY;
CREATE POLICY org_memory_tenant ON org_memory
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE org_memory_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_memory_history FORCE  ROW LEVEL SECURITY;
CREATE POLICY org_memory_history_tenant ON org_memory_history
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE playbook_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_feedback FORCE  ROW LEVEL SECURITY;
CREATE POLICY playbook_feedback_tenant ON playbook_feedback
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE ON org_memory        TO maisha_app;
GRANT SELECT, INSERT, DELETE ON org_memory_history TO maisha_app;
GRANT SELECT, INSERT, UPDATE ON playbook_feedback TO maisha_app;
