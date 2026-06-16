"""Vault FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.vault.schemas import IngestDocument, IngestResult
from app.domains.vault.service import VaultService

router = APIRouter(prefix="/api/vault", tags=["vault"])
_service = VaultService()


@router.post("/documents")
def ingest(body: IngestDocument, db: Session = Depends(get_session)) -> IngestResult:
    result = _service.ingest(
        db,
        file_name=body.file_name,
        content=body.content,
        upload_date=datetime.now(UTC).date().isoformat(),
        doc_type=body.doc_type,
        domain=body.domain,
        entity_id=body.entity_id,
        tags=body.tags,
        uploaded_by=body.uploaded_by,
    )
    db.commit()
    return IngestResult(**result)


@router.get("/search")
def search(q: str, db: Session = Depends(get_session)) -> list[dict]:
    return _service.search(db, q)


@router.post("/fold")
async def fold(
    as_of: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    outcome = await run_loop(
        session=db,
        mahsa=mahsa,
        service=_service,
        timestamp=datetime.now(UTC).isoformat(),
        as_of=anchor,
        action="vault.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "audit_hash": outcome.audit_hash,
    }
