"""Document-vault core — pure, deterministic. SHA-256 content hashing (duplicate detection
+ tamper check), statutory retention policy, classification, and full-text search.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

# Retention classes (PRD §1.12): statutory 7y, operational 3y, permanent (equity/legal).
RETENTION_YEARS = {"statutory": 7, "operational": 3, "permanent": None}

# doc_type -> retention class. Statutory documents (tax/GST/payroll/contracts) keep 7 years;
# equity/legal records are permanent; everything else is operational (3 years).
_STATUTORY_TYPES = {
    "invoice",
    "bill",
    "gst_return",
    "tds_return",
    "challan",
    "payslip",
    "form16",
    "contract",
    "certificate",
    "return",
    "ecr",
}
_PERMANENT_TYPES = {
    "share_certificate",
    "cap_table",
    "board_resolution",
    "moa",
    "aoa",
    "incorporation",
}


def sha256_hex(content: bytes | str) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def retention_class(doc_type: str) -> str:
    if doc_type in _PERMANENT_TYPES:
        return "permanent"
    if doc_type in _STATUTORY_TYPES:
        return "statutory"
    return "operational"


def retention_until(upload_date: str, doc_type: str) -> str | None:
    """ISO date until which the document must be retained, or None for permanent records."""
    years = RETENTION_YEARS[retention_class(doc_type)]
    if years is None:
        return None
    d = date.fromisoformat(upload_date)
    # clamp Feb-29 uploads to Feb-28 on the target year
    try:
        return d.replace(year=d.year + years).isoformat()
    except ValueError:
        return d.replace(year=d.year + years, day=28).isoformat()


def search(documents: list[dict], query: str) -> list[dict]:
    """Case-insensitive substring search over file name, OCR text and tags."""
    q = query.lower()
    hits = []
    for doc in documents:
        haystack = " ".join(
            str(doc.get(f, "") or "") for f in ("file_name", "ocr_text", "tags")
        ).lower()
        if q in haystack:
            hits.append(doc)
    return hits


def verify_integrity(stored_sha256: str, current_content: bytes | str) -> bool:
    """True iff the current content still hashes to the stored digest."""
    return sha256_hex(current_content) == stored_sha256


def find_duplicates(documents: list[dict]) -> dict[str, list[str]]:
    """Group document ids by content hash; entries with >1 id are duplicates."""
    by_hash: dict[str, list[str]] = {}
    for doc in documents:
        by_hash.setdefault(doc["sha256"], []).append(doc["id"])
    return {h: ids for h, ids in by_hash.items() if len(ids) > 1}


def is_retention_overdue(retention_until_iso: str | None, as_of: date) -> bool:
    """True if a non-permanent document is past its retention date (eligible for archival)."""
    if retention_until_iso is None:
        return False
    return date.fromisoformat(retention_until_iso) < as_of


def classify(file_name: str, hint: str | None = None) -> str:
    """Best-effort doc_type from an explicit hint or the file name keywords."""
    if hint:
        return hint
    name = file_name.lower()
    for key in (*_STATUTORY_TYPES, *_PERMANENT_TYPES):
        if key.replace("_", "") in name.replace("_", "").replace("-", ""):
            return key
    return "other"


def build_metrics(documents: list[dict], as_of: date) -> dict[str, Any]:
    """Vault health signals: duplicate count and retention-overdue count. Integrity failures
    are detected on access (need file content), so default 0 here."""
    dupes = find_duplicates(documents)
    overdue = sum(1 for d in documents if is_retention_overdue(d.get("retention_until"), as_of))
    return {
        "documents_count": len(documents),
        "duplicate_groups": len(dupes),
        "retention_overdue": overdue,
        "integrity_failures": 0,
    }
