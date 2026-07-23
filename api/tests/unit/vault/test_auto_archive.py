"""Auto-archive on retention expiry — deferred feature."""

from __future__ import annotations

from app.domains.vault.vault_calc import to_archive


def test_archives_only_expired_retention() -> None:
    docs = [
        {"id": "a", "retention_until": "2025-12-31"},  # past -> archive
        {"id": "b", "retention_until": "2027-12-31"},  # future -> keep
        {"id": "c", "retention_until": None},  # permanent -> never archive
    ]
    assert to_archive(docs, as_of="2026-06-24") == ["a"]


def test_nothing_to_archive() -> None:
    assert to_archive([{"id": "x", "retention_until": "2030-01-01"}], as_of="2026-06-24") == []
