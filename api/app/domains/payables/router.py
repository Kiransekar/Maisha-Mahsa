"""Payables FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.models.payables import Vendor
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.payables.schemas import BillResult, NewBill, NewVendor
from app.domains.payables.service import PayablesService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/payables",
    tags=["payables"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = PayablesService()


@router.post("/vendors", dependencies=[Depends(require(Capability.WRITE))])
def create_vendor(body: NewVendor, db: Session = Depends(get_session)) -> dict[str, int]:
    vendor = Vendor(
        name=body.name,
        gstin=body.gstin,
        pan=body.pan,
        msme_status=1 if body.msme_status else 0,
        payment_terms=body.payment_terms,
        tds_section=body.tds_section,
        payee_type=body.payee_type,
    )
    db.add(vendor)
    db.commit()
    return {"id": vendor.id}


@router.post("/bills", dependencies=[Depends(require(Capability.WRITE))])
def create_bill(body: NewBill, db: Session = Depends(get_session)) -> BillResult:
    try:
        result = _service.create_bill(
            db,
            bill_number=body.bill_number,
            vendor_id=body.vendor_id,
            bill_date=body.bill_date,
            subtotal=body.subtotal,
            igst=body.igst_amount,
            cgst=body.cgst_amount,
            sgst=body.sgst_amount,
            gst_amount=body.gst_amount,
            po_id=body.po_id,
            itc_eligible=body.itc_eligible,
            tds_category=body.tds_category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return BillResult(**result)


@router.get("/ap-aging")
def ap_aging(as_of: str | None = None, db: Session = Depends(get_session)) -> dict:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    return _service.ap_aging(db, anchor)


@router.get("/itc")
def itc(period: str, db: Session = Depends(get_session)) -> dict:
    return _service.input_tax_credit(db, period)


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
        action="payables.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
