"""CITE.P0-1 (SPEC-MEMCITE-1.0 §B1): raw-bytes vault ingest — the document id is the sha256
over the RAW bytes, stored verbatim, integrity covers the bytes, identical bytes dedupe; the
existing text/OCR sha path is untouched. Expected hashes are recomputed independently with
hashlib in each test (mutation-proof: the service cannot grade its own homework)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from app.core.rbac import Role
from app.db.models.vault import Document
from app.domains.vault.service import VaultService

# BOM + CRLF: bytes that do NOT survive a decode/re-encode round-trip unchanged — proves the
# hash is over the raw bytes, never over re-encoded text.
CONTENT = b"\xef\xbb\xbfdate,narration,debit\r\n2026-05-05,NEFT-000123,120000\r\n"


def test_id_is_sha256_of_raw_bytes_and_identical_bytes_dedupe(session):
    svc = VaultService()
    res = svc.ingest_bytes(session, file_name="stmt.csv", content=CONTENT, upload_date="2026-07-01")
    assert res["id"] == hashlib.sha256(CONTENT).hexdigest()
    assert res["sha256"] == res["id"]
    assert res["duplicate"] is False
    # the decoded-text sha would be a DIFFERENT id — raw bytes are the identity
    assert res["id"] != hashlib.sha256(CONTENT.decode("utf-8-sig").encode()).hexdigest()

    dup = svc.ingest_bytes(
        session, file_name="stmt-again.csv", content=CONTENT, upload_date="2026-07-02"
    )
    assert dup["duplicate"] is True
    assert dup["id"] == res["id"]
    assert (session.scalar(select(func.count()).select_from(Document)) or 0) == 1


def test_get_bytes_returns_verbatim_and_fails_loudly_on_tamper(session):
    svc = VaultService()
    res = svc.ingest_bytes(session, file_name="stmt.csv", content=CONTENT, upload_date="2026-07-01")
    assert svc.get_bytes(session, res["id"]) == CONTENT

    session.get(Document, res["id"]).raw_content = CONTENT + b"tampered"
    session.flush()
    with pytest.raises(ValueError, match="integrity"):
        svc.get_bytes(session, res["id"])


def test_text_ocr_path_untouched_and_has_no_raw_bytes(session):
    svc = VaultService()
    res = svc.ingest(session, file_name="note.txt", content="hello vault", upload_date="2026-07-01")
    # text path: id is still the sha over the TEXT (utf-8), exactly as before
    assert res["id"] == hashlib.sha256(b"hello vault").hexdigest()
    assert session.get(Document, res["id"]).raw_content is None
    with pytest.raises(ValueError, match="no stored raw bytes"):
        svc.get_bytes(session, res["id"])


def test_browse_integrity_covers_the_raw_bytes(session):
    svc = VaultService()
    res = svc.ingest_bytes(session, file_name="stmt.csv", content=CONTENT, upload_date="2026-07-01")
    [entry] = svc.browse(session, "stmt", role=Role.OWNER)
    assert entry["integrity_ok"] is True

    session.get(Document, res["id"]).raw_content = CONTENT + b"x"
    session.flush()
    [entry] = svc.browse(session, "stmt", role=Role.OWNER)
    assert entry["integrity_ok"] is False  # loud, not silent
