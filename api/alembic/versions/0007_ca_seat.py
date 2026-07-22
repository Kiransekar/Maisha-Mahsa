"""WS8.3 — memberships.status ('pending' invites) + dev identity mirrors.

Postgres (production path): ``tenant_core.memberships`` (created by 0002) gains ``status``
(existence-guarded per the 0005 pattern; SQL mirrors infra/db/multitenant/006_ca_seat.sql).
Pre-existing rows are real members → 'active'. No new tables; the RLS policy from 0002 covers
the new column automatically (row-level, not column-level).

SQLite (dev/test): the ``app_users`` + ``memberships`` dev-model tables are created from the
live SQLAlchemy models if absent (0006 pattern — 0001_baseline is ``create_all`` from those
same models, so a fresh database already has them, status column included).

Revision ID: 0007_ca_seat
Revises: 0006_ca_threads
Create Date: 2026-07-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_ca_seat"
down_revision = "0006_ca_threads"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        import app.db.models  # noqa: F401  registers all models on Base.metadata
        from app.db.base import Base

        inspector = sa.inspect(bind)
        for name in ("app_users", "memberships"):
            if not inspector.has_table(name):
                Base.metadata.tables[name].create(bind)
        return
    cols = {
        c["name"] for c in sa.inspect(bind).get_columns("memberships", schema=TENANT_SCHEMA)
    }
    if "status" not in cols:
        # verbatim mirror of infra/db/multitenant/006_ca_seat.sql
        op.execute(
            f"ALTER TABLE {TENANT_SCHEMA}.memberships ADD COLUMN status text NOT NULL "
            "DEFAULT 'active' CHECK (status IN ('pending', 'active'))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.drop_table("memberships")
        op.drop_table("app_users")
        return
    op.execute(f"ALTER TABLE {TENANT_SCHEMA}.memberships DROP COLUMN status")
