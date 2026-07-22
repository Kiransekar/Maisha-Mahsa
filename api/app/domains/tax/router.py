"""Tax FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require, require_filing
from app.core.verify import verify_figure
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.tax.schemas import Interest234cInput, TdsReturnInput, TdsReturnResult
from app.domains.tax.service import TaxService, interest_234c_claim
from app.domains.tax.tax_calc import interest_234c

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/tax",
    tags=["tax"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = TaxService()


@router.post("/tds-returns", dependencies=[Depends(require_filing("tds_returns"))])
def file_tds_return(body: TdsReturnInput, db: Session = Depends(get_session)) -> TdsReturnResult:
    result = _service.file_tds_return(
        db,
        return_type=body.return_type,
        quarter=body.quarter,
        due_date=body.due_date,
        total_deducted=body.total_deducted,
        filed_date=body.filed_date,
    )
    db.commit()
    return TdsReturnResult(**result)


@router.get("/tds-summary")
def tds_summary(month: str, db: Session = Depends(get_session)) -> dict:
    return _service.tds_deducted_summary(db, month)


@router.post("/advance-tax/234c")
async def compute_234c(body: Interest234cInput, mahsa: MahsaClient = Depends(get_mahsa)) -> dict:
    # Golden Rule: the s.234C figure reaches the caller only after Mahsa independently
    # recomputes it. A mismatch blocks; Mahsa unreachable raises (never silently unverified).
    result = interest_234c(body.total_liability, body.cumulative_paid)
    claim = interest_234c_claim(body.total_liability, body.cumulative_paid, result["total_234c"])
    verdict = await verify_figure(mahsa, claim)
    return {**result, "verified": verdict.verified, "mahsa_blocked": verdict.blocked}


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
        action="tax.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
