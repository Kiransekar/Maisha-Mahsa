"""P2-2 — itc_register.ims_action: the recipient's IMS accept/reject on an inward invoice.

Nullable TEXT, no default: NULL = no action taken (the IMS "pending" input). Only the ACTION
is stored — the disposition (accepted/rejected/pending/deemed_accepted) is always recomputed
by the WS1.D4 pure state machine (app/domains/gst/ims.py), never persisted, so a rule change
there can never disagree with a stale stored state.

Revision ID: 0009_itc_ims_action
Revises: 0008_job_runs
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_itc_ims_action"
down_revision = "0008_job_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_baseline is `Base.metadata.create_all` from the LIVE models, so on a fresh database
    # the column already exists by the time this revision runs (duplicate-column error without
    # the guard — the 0005 pattern). Pre-existing databases still need the ALTER.
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("itc_register")}
    if "ims_action" not in cols:
        op.add_column("itc_register", sa.Column("ims_action", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("itc_register", "ims_action")
