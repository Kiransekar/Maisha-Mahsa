"""Ledger FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.ledger.schemas import JournalEntryResult, NewAccount, NewJournalEntry
from app.domains.ledger.service import LedgerService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/ledger",
    tags=["ledger"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = LedgerService()


@router.post("/accounts", dependencies=[Depends(require(Capability.WRITE))])
def create_account(body: NewAccount, db: Session = Depends(get_session)) -> dict[str, int]:
    try:
        account_id = _service.create_account(
            db,
            code=body.code,
            name=body.name,
            account_type=body.account_type,
            sub_type=body.sub_type,
            opening_balance=body.opening_balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"id": account_id}


@router.post("/journal", dependencies=[Depends(require(Capability.WRITE))])
def post_journal(body: NewJournalEntry, db: Session = Depends(get_session)) -> JournalEntryResult:
    try:
        result = _service.post_journal_entry(
            db,
            entry_date=body.entry_date,
            description=body.description,
            lines=[ln.model_dump() for ln in body.lines],
            source=body.source,
            reference=body.reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return JournalEntryResult(**result)


@router.get("/trial-balance")
def trial_balance(db: Session = Depends(get_session)) -> dict:
    return _service.trial_balance(db)


@router.get("/pnl")
def pnl(db: Session = Depends(get_session)) -> dict:
    return _service.profit_and_loss(db)


@router.get("/balance-sheet")
def balance_sheet(db: Session = Depends(get_session)) -> dict:
    return _service.balance_sheet(db)


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
        action="ledger.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "audit_hash": outcome.audit_hash,
    }
