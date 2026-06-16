"""Compliance FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.compliance.schemas import MarkFiled, NewDeadline
from app.domains.compliance.service import ComplianceService

router = APIRouter(prefix="/api/compliance", tags=["compliance"])
_service = ComplianceService()


@router.post("/deadlines")
def add_deadline(body: NewDeadline, db: Session = Depends(get_session)) -> dict[str, int]:
    deadline_id = _service.add_deadline(
        db,
        domain=body.domain,
        form_name=body.form_name,
        due_date=body.due_date,
        filing_period=body.filing_period,
    )
    db.commit()
    return {"id": deadline_id}


@router.post("/seed")
def seed_month(month: str, db: Session = Depends(get_session)) -> dict[str, list[int]]:
    ids = _service.seed_month(db, month)
    db.commit()
    return {"ids": ids}


@router.post("/deadlines/{deadline_id}/file")
def mark_filed(
    deadline_id: int, body: MarkFiled, db: Session = Depends(get_session)
) -> dict[str, str]:
    try:
        _service.mark_filed(
            db, deadline_id, filed_date=body.filed_date, acknowledgement=body.acknowledgement
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"status": "filed"}


@router.get("/alerts")
def alerts(as_of: str | None = None, db: Session = Depends(get_session)) -> list[dict]:
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    return _service.alerts(db, anchor)


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
        action="compliance.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }
