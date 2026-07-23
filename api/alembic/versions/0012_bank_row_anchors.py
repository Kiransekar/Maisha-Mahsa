"""CITE.P0-2 (SPEC-MEMCITE-1.0 §B3.1) — cell-level citation anchors on bank_transactions.

Four nullable columns: ``source_doc_id`` (FK documents.id — the vault-ingested statement
file), ``source_row`` (1-based RAW line number in that file), ``row_hash`` (sha256 of
canonical_json over the trimmed cells in column order) and ``occurrence`` (ordinal among
identical rows in the file). The unique ``(source_doc_id, row_hash, occurrence)`` triple
makes re-uploading the same statement a no-op — the previously non-idempotent re-import
(treasury/service.py) is fixed by the same move. Legacy rows keep NULL anchors and render
document-less (no fabricated provenance); NULLs are distinct, so they never collide.

No new table — bank_transactions' existing RLS (tenant path) is unchanged (§0.8).

Revision ID: 0012_bank_row_anchors
Revises: 0011_org_memory
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_bank_row_anchors"
down_revision = "0011_org_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_baseline is `Base.metadata.create_all` from the LIVE models, so on a fresh database
    # the columns + unique constraint already exist by the time this revision runs (0005
    # existence-guard pattern). Pre-existing databases still need the ALTERs.
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("bank_transactions")}
    if "source_doc_id" in cols:
        return
    with op.batch_alter_table("bank_transactions") as batch:
        batch.add_column(sa.Column("source_doc_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("source_row", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("row_hash", sa.String(), nullable=True))
        batch.add_column(sa.Column("occurrence", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_bank_txn_source_doc", "documents", ["source_doc_id"], ["id"])
        batch.create_unique_constraint(
            "uq_bank_txn_anchor", ["source_doc_id", "row_hash", "occurrence"]
        )


def downgrade() -> None:
    with op.batch_alter_table("bank_transactions") as batch:
        batch.drop_constraint("uq_bank_txn_anchor", type_="unique")
        batch.drop_constraint("fk_bank_txn_source_doc", type_="foreignkey")
        batch.drop_column("occurrence")
        batch.drop_column("row_hash")
        batch.drop_column("source_row")
        batch.drop_column("source_doc_id")
