"""CITE.P0-1 / CITE.P0-4 support columns (SPEC-MEMCITE-1.0 §B1, §B3.2).

* ``documents.raw_content`` — the verbatim raw bytes of a content-addressed source file
  (bank CSV, Tally XML). The document id/sha256 hash THESE bytes when present; text/OCR
  documents leave it NULL and keep their existing text-sha identity untouched.
* ``journal_entries.voucher_hash`` + ``journal_entries.source_doc_id`` — the tally_voucher
  citation anchor minted at Tally commit: the content hash of the source voucher and the
  vault-ingested export file it came from. NULL for non-Tally entries.

No new tables — existing RLS is unchanged (§0.8).

Revision ID: 0013_cite_support_columns
Revises: 0012_bank_row_anchors
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_cite_support_columns"
down_revision = "0012_bank_row_anchors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0005 existence-guard pattern: fresh databases already have these via 0001_baseline's
    # create_all from the live models; only pre-existing databases need the ALTERs.
    bind = op.get_bind()
    doc_cols = {c["name"] for c in sa.inspect(bind).get_columns("documents")}
    if "raw_content" not in doc_cols:
        op.add_column("documents", sa.Column("raw_content", sa.LargeBinary(), nullable=True))

    je_cols = {c["name"] for c in sa.inspect(bind).get_columns("journal_entries")}
    if "voucher_hash" not in je_cols:
        with op.batch_alter_table("journal_entries") as batch:
            batch.add_column(sa.Column("voucher_hash", sa.String(), nullable=True))
            batch.add_column(sa.Column("source_doc_id", sa.String(), nullable=True))
            batch.create_foreign_key(
                "fk_journal_entry_source_doc", "documents", ["source_doc_id"], ["id"]
            )


def downgrade() -> None:
    with op.batch_alter_table("journal_entries") as batch:
        batch.drop_constraint("fk_journal_entry_source_doc", type_="foreignkey")
        batch.drop_column("source_doc_id")
        batch.drop_column("voucher_hash")
    op.drop_column("documents", "raw_content")
