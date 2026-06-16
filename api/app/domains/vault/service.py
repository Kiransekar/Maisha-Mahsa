"""Vault service: document ingestion (content-hashed, deduped), classification, retention,
full-text search, integrity verification, and the vault health snapshot for Mahsa.

Vault has no Mahsa sub-vector; Mahsa enforces VAULT-001 (no document integrity failures) on
the snapshot's ``integrity_failures``. The document id IS its SHA-256, so re-ingesting
identical content is detected as a duplicate rather than stored twice.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.vault import Document
from app.domains.vault import vault_calc
from app.domains.vault.manifest import MANIFEST


class VaultService(BaseDomainService):
    domain = "vault"
    keywords = ("document", "vault", "ocr", "scan", "retention", "search", "receipt", "archive")
    manifest = MANIFEST

    # ---- ingestion ------------------------------------------------------------------

    def ingest(
        self,
        session: Session,
        *,
        file_name: str,
        content: str,
        upload_date: str,
        doc_type: str | None = None,
        domain: str | None = None,
        entity_id: str | None = None,
        tags: str | None = None,
        uploaded_by: str | None = None,
    ) -> dict[str, Any]:
        sha = vault_calc.sha256_hex(content)
        existing = session.get(Document, sha)
        if existing is not None:
            return {
                "id": existing.id,
                "sha256": existing.sha256,
                "doc_type": existing.doc_type,
                "retention_until": existing.retention_until,
                "duplicate": True,
            }

        resolved_type = vault_calc.classify(file_name, doc_type)
        retain = vault_calc.retention_until(upload_date, resolved_type)
        doc = Document(
            id=sha,
            file_name=file_name,
            file_path=f"vault/{sha}",
            doc_type=resolved_type,
            domain=domain,
            entity_id=entity_id,
            ocr_text=content,
            upload_date=upload_date,
            retention_until=retain,
            sha256=sha,
            tags=tags,
            uploaded_by=uploaded_by,
            version=1,
        )
        session.add(doc)
        session.flush()
        return {
            "id": sha,
            "sha256": sha,
            "doc_type": resolved_type,
            "retention_until": retain,
            "duplicate": False,
        }

    # ---- access ---------------------------------------------------------------------

    def _docs(self, session: Session) -> list[dict]:
        return [
            {
                "id": d.id,
                "file_name": d.file_name,
                "ocr_text": d.ocr_text,
                "tags": d.tags,
                "sha256": d.sha256,
                "retention_until": d.retention_until,
            }
            for d in session.scalars(select(Document)).all()
        ]

    def search(self, session: Session, query: str) -> list[dict]:
        return vault_calc.search(self._docs(session), query)

    def verify_integrity(self, session: Session, doc_id: str, current_content: str) -> bool:
        doc = session.get(Document, doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")
        return vault_calc.verify_integrity(doc.sha256, current_content)

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        metrics = vault_calc.build_metrics(self._docs(session), anchor)
        return {"as_of": anchor.isoformat(), "metrics": metrics}
