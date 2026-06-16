"""Document vault table (PRD §3.1 / §1.12). The vault owns ``documents``; other modules
(e.g. expense `receipt_document_id`) reference it by id."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # SHA-256 of content
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    upload_date: Mapped[str] = mapped_column(String, nullable=False)
    retention_until: Mapped[str | None] = mapped_column(String)  # None = permanent
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[str | None] = mapped_column(String)
    uploaded_by: Mapped[str | None] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())
