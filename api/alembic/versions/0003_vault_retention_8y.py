"""WS1.C5-migration — recompute stored vault retention_until to 8y from FY-end.

``app.domains.vault.vault_calc.retention_until`` was fixed (§WS1.C5) to count statutory
retention as 8 years from the END OF THE FY of upload, not the upload date, and not the old
7-year figure. That fix only applies going forward to *new* rows; rows written before the fix
still carry the stale value. This migration recomputes ``retention_until`` for every existing
``documents`` row with the CURRENT (correct) function and overwrites only the rows where the
stored value has drifted — permanent-class documents (``retention_until IS NULL``) and
already-correct rows are left untouched, so re-running this against an already-migrated
database is a no-op (idempotent).

Data-only migration (no schema change) — runs identically on SQLite (dev/test) and Postgres.

Revision ID: 0003_vault_retention_8y
Revises: 0002_multitenant_core
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.domains.vault import vault_calc

revision = "0003_vault_retention_8y"
down_revision = "0002_multitenant_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, upload_date, doc_type, retention_until FROM documents")
    ).fetchall()
    for row in rows:
        correct = vault_calc.retention_until(row.upload_date, row.doc_type)
        if correct != row.retention_until:
            bind.execute(
                sa.text("UPDATE documents SET retention_until = :r WHERE id = :id"),
                {"r": correct, "id": row.id},
            )


def downgrade() -> None:
    # Irreversible by design: the pre-migration values were statutorily wrong (7y instead of
    # 8y). There is nothing correct to roll back to, so downgrade is a deliberate no-op.
    pass
