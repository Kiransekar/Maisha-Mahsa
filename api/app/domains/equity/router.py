"""Equity FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.entitlement_deps import require_feature
from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.equity.schemas import NewShareholder, SafeConversionInput, SafeConversionResult
from app.domains.equity.service import EquityService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/equity",
    tags=["equity"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = EquityService()


@router.post(
    "/shareholders",
    dependencies=[Depends(require(Capability.WRITE)), Depends(require_feature("cap_table"))],
)
def add_shareholder(body: NewShareholder, db: Session = Depends(get_session)) -> dict[str, int]:
    sid = _service.add_shareholder(
        db,
        name=body.name,
        category=body.category,
        shares_held=body.shares_held,
        investment_amount=body.investment_amount,
        board_seat=body.board_seat,
    )
    db.commit()
    return {"id": sid}


@router.get("/cap-table", dependencies=[Depends(require_feature("cap_table"))])
def cap_table(db: Session = Depends(get_session)) -> dict:
    return _service.cap_table(db)


@router.post(
    "/safe/convert",
    dependencies=[Depends(require(Capability.WRITE)), Depends(require_feature("safe_notes"))],
)
def convert_safe(body: SafeConversionInput) -> SafeConversionResult:
    return SafeConversionResult(**_service.convert_safe(**body.model_dump()))


@router.post(
    "/snapshot",
    dependencies=[
        Depends(require(Capability.WRITE)),
        Depends(require_feature("cap_table_snapshot")),
    ],
)
def snapshot(
    snapshot_date: str, esop_board_approved: bool = True, db: Session = Depends(get_session)
) -> dict[str, int]:
    sid = _service.snapshot_cap_table(
        db, snapshot_date=snapshot_date, esop_board_approved=esop_board_approved
    )
    db.commit()
    return {"id": sid}


@router.post("/fold", dependencies=[Depends(require_feature("cap_table"))])
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
        action="equity.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
