"""WS4.5 — job_run idempotency ledger, WITH its RLS policy in this same revision (§0.8).

Postgres (production path): the table lands in ``tenant_core`` via the inlined SQL below — a
verbatim snapshot of ``infra/db/multitenant/007_job_runs.sql`` as of this revision (0006
pattern: inlined, not read from disk, so later edits to that file can never silently change
what this revision *was*).

SQLite (dev/test): the ``job_run`` + ``orgs`` dev-model tables are created from the live
SQLAlchemy models if absent, existence-guarded per the 0005 pattern (``orgs`` is created here
because the tenant-iterated jobs read it; a fresh DB already has both via 0001's create_all).

Revision ID: 0008_job_runs
Revises: 0007_ca_seat
Create Date: 2026-07-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_job_runs"
down_revision = "0007_ca_seat"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


# ---- snapshot of infra/db/multitenant/007_job_runs.sql -----------------------------------
_007_SQL = """
CREATE TABLE job_run (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id   uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  job      text NOT NULL,
  period   text NOT NULL,
  status   text NOT NULL CHECK (status IN ('done', 'error')),
  ran_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, job, period)
);

ALTER TABLE job_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_run FORCE  ROW LEVEL SECURITY;
CREATE POLICY job_run_tenant ON job_run
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE ON job_run TO maisha_app;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        import app.db.models  # noqa: F401  registers all models on Base.metadata
        from app.db.base import Base

        inspector = sa.inspect(bind)
        for name in ("orgs", "job_run"):
            if not inspector.has_table(name):
                Base.metadata.tables[name].create(bind)
        return
    if sa.inspect(bind).has_table("job_run", schema=TENANT_SCHEMA):
        return  # existence guard: already applied (e.g. schema pre-provisioned from the .sql)
    op.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
    op.execute(_007_SQL)
    op.execute("SET search_path TO public")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.drop_table("job_run")
        return
    op.execute(f"DROP TABLE IF EXISTS {TENANT_SCHEMA}.job_run")
