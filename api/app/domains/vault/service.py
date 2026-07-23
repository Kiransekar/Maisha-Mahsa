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

from app.core import ocr
from app.core.domain import BaseDomainService
from app.core.landing import can_view_sensitivity
from app.core.rbac import Role
from app.db.models.vault import Document
from app.domains.vault import vault_calc
from app.domains.vault.manifest import MANIFEST


class VaultService(BaseDomainService):
    domain = "vault"
    keywords = ("document", "vault", "ocr", "scan", "retention", "search", "receipt", "archive")
    manifest = MANIFEST

    def ingest_image(
        self, session: Session, *, file_name: str, image_bytes: bytes, upload_date: str
    ) -> dict[str, Any]:
        """Scan/photo → OCR text → ingest (the text becomes the searchable, hash-chained
        content). Raises ``OcrUnavailable`` when Tesseract isn't installed."""
        text = ocr.image_to_text(image_bytes)
        return self.ingest(
            session, file_name=file_name, content=text, upload_date=upload_date, doc_type="scan"
        )

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
                "doc_type": d.doc_type,
                "retention_until": d.retention_until,
            }
            for d in session.scalars(select(Document)).all()
        ]

    def search(self, session: Session, query: str) -> list[dict]:
        return vault_calc.search(self._docs(session), query)

    def browse(
        self, session: Session, query: str, *, role: Role, as_of: date | None = None
    ) -> list[dict]:
        """P2-1 vault browser: full-text search (``vault_calc.search``, unchanged) enriched
        with the per-doc facts the UI needs to render loudly — SHA-256 integrity state and
        retention-overdue — then passed through the ONE canonical clearance lattice
        (``app.core.landing.can_view_sensitivity``, per its own docstring: vault access should
        route through it rather than the legacy standalone ``vault_calc`` role ranks). A doc
        above the caller's clearance still APPEARS (existence is not a secret) but with its
        content stripped and a reason — the same hidden-not-absent shape T11 uses for figures.
        """
        anchor = as_of or date.today()
        out: list[dict] = []
        for d in vault_calc.search(self._docs(session), query):
            sensitivity = vault_calc.document_sensitivity(d.get("doc_type") or "other")
            entry: dict[str, Any] = {
                "id": d["id"],
                "file_name": d["file_name"],
                "doc_type": d.get("doc_type"),
                "sensitivity": sensitivity,
                "retention_until": d.get("retention_until"),
                "retention_overdue": vault_calc.is_retention_overdue(
                    d.get("retention_until"), anchor
                ),
            }
            if can_view_sensitivity(role, sensitivity):
                entry["restricted"] = False
                entry["tags"] = d.get("tags")
                entry["integrity_ok"] = vault_calc.verify_integrity(
                    d["sha256"], d.get("ocr_text") or ""
                )
            else:
                entry["restricted"] = True
                entry["reason"] = f"requires {sensitivity} clearance"
            out.append(entry)
        return out

    def verify_integrity(self, session: Session, doc_id: str, current_content: str) -> bool:
        doc = session.get(Document, doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")
        return vault_calc.verify_integrity(doc.sha256, current_content)

    # ---- RBAC access control --------------------------------------------------------

    def can_access(self, role: str, action: str, *, sensitivity: str = "internal") -> bool:
        """Whether ``role`` may perform ``action`` on a document of this sensitivity."""
        return vault_calc.can_access(role, action, sensitivity=sensitivity)

    def accessible_documents(self, session: Session, role: str) -> list[dict]:
        """Documents the role may read, each tagged with its derived sensitivity."""
        out = []
        for d in session.scalars(select(Document)).all():
            sensitivity = vault_calc.document_sensitivity(d.doc_type or "other")
            if vault_calc.can_access(role, "read", sensitivity=sensitivity):
                out.append({"id": d.id, "file_name": d.file_name, "sensitivity": sensitivity})
        return out

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        metrics = vault_calc.build_metrics(self._docs(session), anchor)
        return {"as_of": anchor.isoformat(), "metrics": metrics}
