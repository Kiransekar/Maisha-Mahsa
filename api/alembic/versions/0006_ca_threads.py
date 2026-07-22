"""WS8.2 — ca_thread + ca_thread_event tables, WITH their RLS policies in this same revision
(§0.8), following 0004_legal_acceptance's pattern exactly.

Postgres (production path): the tables land in ``tenant_core`` via the inlined SQL below — a
verbatim snapshot of ``infra/db/multitenant/005_ca_threads.sql`` as of this revision (the SQL is
inlined, not read from disk, so later edits to that file can never silently change what this
revision *was*; any change is a NEW revision). Each table ships with ENABLE ROW LEVEL SECURITY +
its policy here, so ``scripts/check_rls_coverage.sh`` holds on the alembic path.

SQLite (dev/test): no RLS/roles/uuid-gen — the dev-model tables are created from the live
SQLAlchemy models, guarded with existence checks because ``0001_baseline`` is ``create_all``
from those same models (on a fresh database the tables already exist by the time this revision
runs — the 0005_decision_item_id lesson).

Revision ID: 0006_ca_threads
Revises: 0005_decision_item_id
Create Date: 2026-07-22
"""

# ruff: noqa: E501 — the SQL below is a verbatim snapshot of infra/db/multitenant/005_ca_threads.sql;
# reflowing it would break the byte-for-byte correspondence that makes it reviewable.
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_ca_threads"
down_revision = "0005_decision_item_id"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


# ---- snapshot of infra/db/multitenant/005_ca_threads.sql ---------------------------------
_005_SQL = """
CREATE TABLE ca_thread (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  domain      text NOT NULL,
  entry_ref   text NOT NULL,
  question    text NOT NULL,
  state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'responded', 'resolved')),
  raised_by   uuid NOT NULL REFERENCES app_users(id)
);
CREATE INDEX ca_thread_lookup ON ca_thread(org_id, state);

ALTER TABLE ca_thread ENABLE ROW LEVEL SECURITY;
ALTER TABLE ca_thread FORCE  ROW LEVEL SECURITY;
CREATE POLICY ca_thread_tenant ON ca_thread
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON ca_thread TO maisha_app;
GRANT UPDATE (state) ON ca_thread TO maisha_app;

CREATE TABLE ca_thread_event (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  thread_id   uuid NOT NULL REFERENCES ca_thread(id) ON DELETE CASCADE,
  timestamp   timestamptz NOT NULL DEFAULT now(),
  event       text NOT NULL CHECK (event IN ('raise', 'respond', 'resolve')),
  user_id     uuid NOT NULL REFERENCES app_users(id),
  note        text,
  doc_id      text,
  audit_hash  text
);
CREATE INDEX ca_thread_event_lookup ON ca_thread_event(org_id, thread_id);

ALTER TABLE ca_thread_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE ca_thread_event FORCE  ROW LEVEL SECURITY;
CREATE POLICY ca_thread_event_tenant ON ca_thread_event
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON ca_thread_event TO maisha_app;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite dev/test: create the dev-model tables only if 0001's create_all (fresh DB) or a
        # previous run hasn't already (existence-guarded per the 0005 pattern).
        import app.db.models  # noqa: F401  registers all models on Base.metadata
        from app.db.base import Base

        inspector = sa.inspect(bind)
        for name in ("ca_thread", "ca_thread_event"):
            if not inspector.has_table(name):
                Base.metadata.tables[name].create(bind)
        return
    if sa.inspect(bind).has_table("ca_thread", schema=TENANT_SCHEMA):
        return  # existence guard: already applied (e.g. schema pre-provisioned from the .sql)
    op.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
    op.execute(_005_SQL)
    op.execute("SET search_path TO public")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.drop_table("ca_thread_event")
        op.drop_table("ca_thread")
        return
    op.execute(f"DROP TABLE IF EXISTS {TENANT_SCHEMA}.ca_thread_event")
    op.execute(f"DROP TABLE IF EXISTS {TENANT_SCHEMA}.ca_thread")
