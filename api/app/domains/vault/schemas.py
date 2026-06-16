"""Pydantic request/response models for the vault API."""

from __future__ import annotations

from pydantic import BaseModel


class IngestDocument(BaseModel):
    file_name: str
    content: str  # raw text or OCR text (image→text is the stubbed boundary)
    doc_type: str | None = None
    domain: str | None = None
    entity_id: str | None = None
    tags: str | None = None
    uploaded_by: str | None = None


class IngestResult(BaseModel):
    id: str
    sha256: str
    doc_type: str
    retention_until: str | None
    duplicate: bool
