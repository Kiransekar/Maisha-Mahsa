"""Treasury FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.models.treasury import BankAccount
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.treasury.schemas import AccountSummary
from app.domains.treasury.service import TreasuryService

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/treasury",
    tags=["treasury"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = TreasuryService()


class NewAccount(BaseModel):
    bank_name: str
    account_number: str
    ifsc: str
    opening_balance_paise: int = 0


@router.post("/accounts", dependencies=[Depends(require(Capability.WRITE))])
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


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_session)) -> list[AccountSummary]:
    """P0-5: the re-import target picker on the treasury domain screen needs a real account id
    to import into — this is the only place that existed to get one (creation returns an id,
    but nothing previously listed the accounts already on file)."""
    accounts = db.scalars(select(BankAccount)).all()
    return [
        AccountSummary(
            id=a.id,
            bank_name=a.bank_name,
            account_number=a.account_number,
            current_balance_paise=a.current_balance,
        )
        for a in accounts
    ]


@router.post("/accounts/{account_id}/import", dependencies=[Depends(require(Capability.WRITE))])
async def import_statement(
    account_id: int, file: UploadFile, db: Session = Depends(get_session)
) -> dict[str, int]:
    data = await file.read()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="file is not UTF-8 text — is this a CSV export?"
        ) from exc
    try:
        # CITE.P0-2: the ORIGINAL bytes go to the vault (content-addressed anchor target);
        # the decoded text is what gets parsed. Time is injected here, at the edge.
        result = _service.import_csv(
            db,
            account_id,
            text,
            file_name=file.filename or "bank-statement.csv",
            raw_bytes=data,
            upload_date=datetime.now(UTC).date().isoformat(),
        )
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
