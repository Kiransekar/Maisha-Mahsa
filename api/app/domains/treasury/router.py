"""Treasury FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.db.models.treasury import BankAccount
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.treasury.service import TreasuryService

router = APIRouter(prefix="/api/treasury", tags=["treasury"])
_service = TreasuryService()


class NewAccount(BaseModel):
    bank_name: str
    account_number: str
    ifsc: str
    opening_balance_paise: int = 0


@router.post("/accounts")
def create_account(body: NewAccount, db: Session = Depends(get_session)) -> dict[str, int]:
    acct = BankAccount(
        bank_name=body.bank_name,
        account_number=body.account_number,
        ifsc=body.ifsc,
        opening_balance=body.opening_balance_paise,
        current_balance=body.opening_balance_paise,
    )
    db.add(acct)
    db.commit()
    return {"id": acct.id}


@router.post("/accounts/{account_id}/import")
async def import_statement(
    account_id: int, file: UploadFile, db: Session = Depends(get_session)
) -> dict[str, int]:
    raw = (await file.read()).decode("utf-8-sig")
    try:
        result = _service.import_csv(db, account_id, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.get("/cash")
def cash(db: Session = Depends(get_session)) -> dict:
    return _service.cash_position(db)


@router.get("/metrics")
def metrics(as_of: str | None = None, db: Session = Depends(get_session)) -> dict:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    return _service.metrics(db, anchor)


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
        action="treasury.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "global_intent": outcome.fold.global_intent,
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
