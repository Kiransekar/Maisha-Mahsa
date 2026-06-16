"""Revenue FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.db.models.revenue import Customer
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.revenue.schemas import InvoiceResult, NewCustomer, NewInvoice
from app.domains.revenue.service import RevenueService

router = APIRouter(prefix="/api/revenue", tags=["revenue"])
_service = RevenueService()


@router.post("/customers")
def create_customer(body: NewCustomer, db: Session = Depends(get_session)) -> dict[str, int]:
    cust = Customer(
        name=body.name,
        gstin=body.gstin,
        pan=body.pan,
        state=body.state,
        payment_terms=body.payment_terms,
        tds_applicable=1 if body.tds_applicable else 0,
        tds_rate=body.tds_rate,
    )
    db.add(cust)
    db.commit()
    return {"id": cust.id}


@router.post("/invoices")
def create_invoice(body: NewInvoice, db: Session = Depends(get_session)) -> InvoiceResult:
    try:
        result = _service.create_invoice(
            db,
            invoice_number=body.invoice_number,
            customer_id=body.customer_id,
            invoice_date=body.invoice_date,
            lines=[ln.model_dump() for ln in body.lines],
            gst_rate=body.gst_rate,
            irn=body.irn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return InvoiceResult(**result)


@router.get("/ar-aging")
def ar_aging(as_of: str | None = None, db: Session = Depends(get_session)) -> dict:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    return _service.ar_aging(db, anchor)


@router.get("/dunning")
def dunning(as_of: str | None = None, db: Session = Depends(get_session)) -> list[dict]:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    return _service.due_dunning(db, anchor)


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
        action="revenue.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
