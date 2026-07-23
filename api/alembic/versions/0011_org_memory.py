"""SPEC-MEMCITE-1.0 MEM.P0-1 — org_memory + org_memory_history + playbook_feedback (+RLS, §0.8).

Two schema paths, the way 0004/0005/0010 established:

* **Postgres (production, tenant_core)** — the SQL is INLINED as a verbatim snapshot of
  ``infra/db/multitenant/009_org_memory.sql`` (a migration's content must be immutable; the
  .sql file stays the reviewable/red-team source and the RLS-coverage-gate input; any later
  change is a NEW revision). Creates the three tenant tables with RLS + a policy each in this
  SAME revision — the §0.8 rule ``scripts/check_rls_coverage.sh`` enforces on both paths.
* **SQLite (dev/test)** — the 0005 existence-guard pattern: ``0001_baseline`` is
  ``Base.metadata.create_all`` from the LIVE models, so a fresh database already has the
  tables when this revision runs; a pre-existing dev database migrated before the model
  change still needs the CREATE.

Revision ID: 0011_org_memory
Revises: 0010_dpdp_rights
Create Date: 2026-07-23
"""

# ruff: noqa: E501 — the SQL below is a verbatim snapshot; reflowing it would break the
# byte-for-byte correspondence with infra/db/multitenant/009_org_memory.sql that makes it reviewable.
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_org_memory"
down_revision = "0010_dpdp_rights"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


# ---- snapshot of infra/db/multitenant/009_org_memory.sql ---------------------------------
_009_SQL = """
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
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
        op.execute(_009_SQL)
        op.execute("SET search_path TO public")
        return
    # SQLite (dev/test): 0005 existence-guard — fresh DBs already have the tables via the
    # 0001 create_all baseline; only an older migrated dev DB needs the CREATEs.
    from app.db.models.memory import OrgMemory, OrgMemoryHistory, PlaybookFeedback

    existing = set(sa.inspect(bind).get_table_names())
    for model in (OrgMemory, OrgMemoryHistory, PlaybookFeedback):
        if model.__tablename__ not in existing:
            model.__table__.create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("playbook_feedback", "org_memory_history", "org_memory"):
            op.execute(f"DROP TABLE IF EXISTS {TENANT_SCHEMA}.{table}")
        return
    for table in ("playbook_feedback", "org_memory_history", "org_memory"):
        op.drop_table(table)
