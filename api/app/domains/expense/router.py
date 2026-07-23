"""Expense FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.ocr import OcrUnavailable
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.expense.schemas import ClaimResult, NewClaim, ReceiptText
from app.domains.expense.service import ExpenseService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/expense",
    tags=["expense"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = ExpenseService()


@router.post("/claims", dependencies=[Depends(require(Capability.WRITE))])
def submit_claim(body: NewClaim, db: Session = Depends(get_session)) -> ClaimResult:
    result = _service.submit_claim(
        db,
        claim_date=body.claim_date,
        expense_date=body.expense_date,
        category=body.category,
        amount=body.amount,
        gst_amount=body.gst_amount,
        employee_id=body.employee_id,
        vendor_name=body.vendor_name,
        description=body.description,
    )
    db.commit()
    return ClaimResult(**result)


@router.post(
    "/claims/{claim_id}/approve", dependencies=[Depends(require(Capability.APPROVE_PAYMENT))]
)
def approve(claim_id: int, approver: str, db: Session = Depends(get_session)) -> dict[str, str]:
    try:
        _service.approve_claim(
            db, claim_id, approver=approver, approved_date=datetime.now(UTC).date().isoformat()
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"status": "approved"}


@router.get("/analytics")
def analytics(db: Session = Depends(get_session)) -> dict:
    return _service.category_spend(db)


@router.post("/parse-receipt")
def parse_receipt(body: ReceiptText) -> dict:
    return _service.parse_receipt(body.ocr_text)


@router.post("/ocr-receipt")
async def ocr_receipt(file: UploadFile = File(...)) -> dict:
    """P1-8 — thin JSON wrapper over the SAME handler ``/d/expense/ocr-receipt`` calls
    (``ExpenseService.ocr_capture``): one parser, so the SPA and the HTMX drawer can never see
    different fields for the same photo. Read-only (router baseline) — OCR never mutates a
    claim; the parsed {amount_paise, gstin, date} only prefill an editable form field on the
    client, never a committed value."""
    try:
        return _service.ocr_capture(await file.read())
    except OcrUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
        action="expense.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "audit_hash": outcome.audit_hash,
    }
