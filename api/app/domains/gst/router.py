"""GST FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require, require_filing
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.gst.gst_calc import validate_gstin
from app.domains.gst.schemas import Gstr1Input, Gstr3bInput, Gstr3bResult
from app.domains.gst.service import GstService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/gst",
    tags=["gst"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = GstService()


@router.get("/validate-gstin")
def check_gstin(gstin: str) -> dict[str, bool]:
    return {"valid": validate_gstin(gstin)}


@router.post("/gstr3b", dependencies=[Depends(require_filing("gstr3b"))])
def file_gstr3b(body: Gstr3bInput, db: Session = Depends(get_session)) -> Gstr3bResult:
    result = _service.file_gstr3b(
        db,
        filing_period=body.filing_period,
        due_date=body.due_date,
        output=body.output.model_dump(),
        itc_available=body.itc_available.model_dump(),
        filed_date=body.filed_date,
        is_nil=body.is_nil,
        aato=body.aato,
    )
    db.commit()
    return Gstr3bResult(**result)


@router.post("/gstr1")
def build_gstr1(body: Gstr1Input) -> dict:
    lines = [ln.model_dump() for ln in body.lines]
    return _service.build_gstr1(lines, filing_period=body.filing_period)


@router.get("/itc/reconcile")
def reconcile(db: Session = Depends(get_session)) -> dict:
    return _service.reconcile_itc(db)


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
        action="gst.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
