"""WS7-E2E fix:bulk-rows — decision.item_id: WHICH inbox row a decision covered.

Without it, two previewed rows in one domain sealed two byte-identical domain-level
decisions. Nullable TEXT, no default: pre-fix rows and whole-domain decisions from the
approvals page stay NULL. History is never mutated — the audit chain's row identity lives
inside the hashed ``query`` field of new entries; this column is the queryable mirror.

Revision ID: 0005_decision_item_id
Revises: 0004_legal_acceptance
Create Date: 2026-07-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_decision_item_id"
down_revision = "0004_legal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_baseline is `Base.metadata.create_all` from the LIVE models, so on a fresh database
    # the column already exists by the time this revision runs (duplicate-column error without
    # the guard). Pre-existing databases migrated before the model change still need the ALTER.
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("decision")}
    if "item_id" not in cols:
        op.add_column("decision", sa.Column("item_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("decision", "item_id")
