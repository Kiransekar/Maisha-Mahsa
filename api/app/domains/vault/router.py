"""Vault FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.ocr import OcrUnavailable
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.vault.schemas import IngestDocument, IngestResult
from app.domains.vault.service import VaultService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/vault",
    tags=["vault"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = VaultService()


@router.post("/documents", dependencies=[Depends(require(Capability.WRITE))])
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
def search(
    q: str,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_session),
) -> list[dict]:
    """P2-1 vault browser: also the document LIST (an empty ``q`` matches every doc — see
    ``vault_calc.search``). Sensitivity-masked per the caller's role — see ``VaultService.browse``.
    Router-level ``read`` baseline unchanged; ``resolve_principal`` only reads the already-
    verified caller, same pattern as the other role-aware read routes in app/web/api_domains.py.
    """
    return _service.browse(db, q, role=principal.role, as_of=datetime.now(UTC).date())


@router.post("/ocr-ingest", dependencies=[Depends(require(Capability.WRITE))])
async def ocr_ingest(
    file: UploadFile = File(...),
    upload_date: str = Form(...),
    db: Session = Depends(get_session),
) -> IngestResult:
    """Thin JSON wrapper over the SAME ``VaultService.ingest_image`` the pre-existing
    ``/d/vault/ocr-ingest`` HTMX route calls (app/main.py) — one OCR→ingest parser, so the SPA
    and the HTMX drawer can never see different fields for the same photo."""
    try:
        result = _service.ingest_image(
            db,
            file_name=file.filename or "scan",
            image_bytes=await file.read(),
            upload_date=upload_date,
        )
    except OcrUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return IngestResult(**result)


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
