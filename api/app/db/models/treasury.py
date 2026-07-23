"""Treasury domain tables (PRD §3.2). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bank_name: Mapped[str] = mapped_column(String, nullable=False)
    account_number: Mapped[str] = mapped_column(String, nullable=False)
    ifsc: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[str | None] = mapped_column(String)
    opening_balance: Mapped[int] = mapped_column(Integer, default=0)  # paise
    current_balance: Mapped[int] = mapped_column(Integer, default=0)  # paise
    currency: Mapped[str] = mapped_column(String, default="INR")
    is_primary: Mapped[int] = mapped_column(Integer, default=0)
    last_sync: Mapped[str | None] = mapped_column(String)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    # SPEC-MEMCITE-1.0 CITE.P0-2: re-uploading the same statement file is a no-op — the
    # anchor triple is unique per source document. Legacy rows keep NULL anchors (SQLite and
    # Postgres both treat NULLs as distinct, so pre-anchor rows never collide).
    __table_args__ = (
        UniqueConstraint("source_doc_id", "row_hash", "occurrence", name="uq_bank_txn_anchor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"), nullable=False)
    txn_date: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    reference: Mapped[str | None] = mapped_column(String)
    debit: Mapped[int] = mapped_column(Integer, default=0)  # paise
    credit: Mapped[int] = mapped_column(Integer, default=0)  # paise
    balance: Mapped[int | None] = mapped_column(Integer)  # paise
    category: Mapped[str | None] = mapped_column(String)
    matched_invoice_id: Mapped[int | None] = mapped_column(Integer)
    matched_vendor_id: Mapped[int | None] = mapped_column(Integer)
    is_reconciled: Mapped[int] = mapped_column(Integer, default=0)
    # CITE.P0-2 cell-level citation anchor (SPEC-MEMCITE-1.0 §B1/§B3): the vault document the
    # row came from, its 1-based RAW source line, the sha256 of canonical_json([trimmed cells
    # in column order]), and the ordinal among identical rows in that file. All nullable —
    # legacy rows have no anchors and must render document-less (no fabricated provenance).
    source_doc_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    source_row: Mapped[int | None] = mapped_column(Integer)
    row_hash: Mapped[str | None] = mapped_column(String)
    occurrence: Mapped[int | None] = mapped_column(Integer)


class FixedDeposit(Base):
    __tablename__ = "fixed_deposits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    fd_number: Mapped[str] = mapped_column(String, nullable=False)
    principal: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    interest_rate: Mapped[float] = mapped_column(nullable=False)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    maturity_date: Mapped[str] = mapped_column(String, nullable=False)
    maturity_amount: Mapped[int | None] = mapped_column(Integer)  # paise
    tds_deducted: Mapped[int] = mapped_column(Integer, default=0)  # paise
    status: Mapped[str] = mapped_column(String, default="active")
