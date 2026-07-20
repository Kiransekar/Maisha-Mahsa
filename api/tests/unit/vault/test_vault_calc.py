"""Document-vault checks — hashing, retention, search, integrity, dedup, classification."""

from datetime import date

from app.domains.vault import vault_calc as v


def test_sha256_is_stable_and_content_addressed():
    assert v.sha256_hex("hello") == v.sha256_hex("hello")
    assert v.sha256_hex("hello") != v.sha256_hex("world")
    assert len(v.sha256_hex(b"bytes")) == 64


def test_retention_classes():
    # statutory (invoice) -> 8 years from FY-end (§WS1.C5): FY of 2026-05-10 ends 2027-03-31
    assert v.retention_until("2026-05-10", "invoice") == "2035-03-31"
    # a Jan-Mar upload sits in the FY ending that same 31 Mar
    assert v.retention_until("2026-02-10", "invoice") == "2034-03-31"
    # operational (other) -> 3 years from upload date (unchanged)
    assert v.retention_until("2026-05-10", "other") == "2029-05-10"
    # permanent (share certificate) -> None
    assert v.retention_until("2026-05-10", "share_certificate") is None


def test_search_matches_ocr_and_tags():
    docs = [
        {"id": "1", "file_name": "inv1.pdf", "ocr_text": "TASTY CAFE total 600", "tags": "meals"},
        {"id": "2", "file_name": "rent.pdf", "ocr_text": "office rent", "tags": "rent"},
    ]
    assert [d["id"] for d in v.search(docs, "cafe")] == ["1"]
    assert [d["id"] for d in v.search(docs, "rent")] == ["2"]
    assert v.search(docs, "nonexistent") == []


def test_verify_integrity():
    sha = v.sha256_hex("contract text")
    assert v.verify_integrity(sha, "contract text") is True
    assert v.verify_integrity(sha, "tampered text") is False


def test_find_duplicates():
    docs = [
        {"id": "a", "sha256": "X"},
        {"id": "b", "sha256": "X"},
        {"id": "c", "sha256": "Y"},
    ]
    dupes = v.find_duplicates(docs)
    assert dupes == {"X": ["a", "b"]}


def test_retention_overdue_and_classify():
    assert v.is_retention_overdue("2025-01-01", date(2026, 6, 16)) is True
    assert v.is_retention_overdue("2030-01-01", date(2026, 6, 16)) is False
    assert v.is_retention_overdue(None, date(2026, 6, 16)) is False  # permanent never overdue
    assert v.classify("May_invoice.pdf") == "invoice"
    assert v.classify("random.pdf") == "other"
