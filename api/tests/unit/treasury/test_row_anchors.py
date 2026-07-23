"""CITE.P0-2 (SPEC-MEMCITE-1.0 §B3.1): bank CSV import is vault-first, cell-citable and
idempotent. Every expected value (document sha, row hashes, source line numbers) is recomputed
independently in the tests with hashlib/json — never via the code under test."""

from __future__ import annotations

import csv
import hashlib
import json

from sqlalchemy import func, select

from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.db.models.vault import Document
from app.domains.treasury.service import TreasuryService
from app.domains.vault.service import VaultService

# Blank line between rows: RAW source line numbers (CSVW source-number semantics) must still
# advance — header=1, first row=2, blank=3, second row=4. The padded cells on line 4 prove the
# hash is over TRIMMED cells (spec §B1), not the raw field bytes.
CSV_TEXT = (
    "date,description,reference,debit,credit,balance\n"
    "2026-05-05,Opening,REF1,0,100000,100000\n"
    "\n"
    "2026-05-10, AWS invoice ,REF2,20000,0, 80000\n"
)

# Two byte-identical NEFT rows — genuine duplicates distinguished only by occurrence.
CSV_TWINS = (
    "date,description,reference,debit,credit\n"
    "2026-05-05,NEFT UPI,REF9,0,50000\n"
    "2026-05-05,NEFT UPI,REF9,0,50000\n"
)


def _row_hash(cells: list[str]) -> str:
    """Independent recompute: sha256(canonical_json([trimmed cells in column order]))."""
    payload = json.dumps(
        [c.strip() for c in cells], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _account(session, balance_paise: int = 0) -> BankAccount:
    acct = BankAccount(
        bank_name="HDFC",
        account_number="0001",
        ifsc="HDFC0000001",
        opening_balance=balance_paise,
        current_balance=balance_paise,
    )
    session.add(acct)
    session.flush()
    return acct


def _txns(session) -> list[BankTransaction]:
    return list(session.scalars(select(BankTransaction).order_by(BankTransaction.id)).all())


def test_import_mints_anchors_with_raw_line_numbers_and_content_hashes(session):
    svc = TreasuryService()
    acct = _account(session)
    result = svc.import_csv(session, acct.id, CSV_TEXT, file_name="hdfc-may.csv")
    assert result["rows_imported"] == 2

    doc_sha = hashlib.sha256(CSV_TEXT.encode("utf-8")).hexdigest()
    doc = session.get(Document, doc_sha)
    assert doc is not None, "vault-first: the source CSV must be a content-addressed document"
    assert doc.raw_content == CSV_TEXT.encode("utf-8")
    assert doc.file_name == "hdfc-may.csv"

    txns = _txns(session)
    assert [t.source_row for t in txns] == [2, 4]  # raw line numbers, blank line counted
    assert [t.source_doc_id for t in txns] == [doc_sha, doc_sha]
    assert [t.occurrence for t in txns] == [1, 1]
    assert txns[0].row_hash == _row_hash(["2026-05-05", "Opening", "REF1", "0", "100000", "100000"])
    assert txns[1].row_hash == _row_hash(
        ["2026-05-10", "AWS invoice", "REF2", "20000", "0", "80000"]
    )


def test_reupload_is_a_noop_for_rows_and_balance(session):
    svc = TreasuryService()
    acct = _account(session)
    first = svc.import_csv(session, acct.id, CSV_TEXT)
    assert first["rows_imported"] == 2
    assert acct.current_balance == Paise.from_rupees(80000)

    again = svc.import_csv(session, acct.id, CSV_TEXT)
    assert again["rows_imported"] == 0
    assert again["rows_duplicate"] == 2
    assert again["closing_balance_paise"] == Paise.from_rupees(80000)
    assert acct.current_balance == Paise.from_rupees(80000)
    count = session.scalar(select(func.count()).select_from(BankTransaction)) or 0
    assert count == 2, "re-uploading the same statement must not duplicate rows"


def test_identical_rows_get_occurrence_1_and_2_and_still_dedupe(session):
    svc = TreasuryService()
    acct = _account(session)
    result = svc.import_csv(session, acct.id, CSV_TWINS)
    assert result["rows_imported"] == 2

    txns = _txns(session)
    expected = _row_hash(["2026-05-05", "NEFT UPI", "REF9", "0", "50000"])
    assert [t.row_hash for t in txns] == [expected, expected]
    assert [t.occurrence for t in txns] == [1, 2]

    again = svc.import_csv(session, acct.id, CSV_TWINS)
    assert again["rows_imported"] == 0
    assert again["rows_duplicate"] == 2
    assert (session.scalar(select(func.count()).select_from(BankTransaction)) or 0) == 2


def test_anchors_round_trip_against_the_stored_file(session):
    """§B2 resolvability: fetch the vault bytes, re-extract at each anchor's source line,
    recompute the row hash — it must equal the stored one."""
    svc = TreasuryService()
    acct = _account(session)
    svc.import_csv(session, acct.id, CSV_TEXT)

    doc_sha = hashlib.sha256(CSV_TEXT.encode("utf-8")).hexdigest()
    raw = VaultService().get_bytes(session, doc_sha)  # integrity-checked fetch
    lines = raw.decode("utf-8-sig").splitlines()
    for t in _txns(session):
        source_line = lines[t.source_row - 1]
        cells = next(csv.reader([source_line]))
        assert _row_hash(cells) == t.row_hash


def test_unimportable_csv_mints_nothing_and_no_document(session):
    """No fabricated provenance: a file with zero importable rows leaves no anchors and no
    vault document behind."""
    svc = TreasuryService()
    acct = _account(session)
    result = svc.import_csv(session, acct.id, "date,debit\nnot-a-date,10\n")
    assert result["rows_imported"] == 0
    assert result["rows_skipped"] == 1
    assert (session.scalar(select(func.count()).select_from(Document)) or 0) == 0
