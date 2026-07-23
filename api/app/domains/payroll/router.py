"""Payroll FastAPI routes (thin — delegate to the service and the loop)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import legal
from app.core.entitlement_deps import entitlement_payload, require_feature
from app.core.entitlements import GuardDecision
from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.principal import current_user
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.models.payroll import Employee
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.payroll.schemas import NewEmployee, PayrollRunResult, SalaryInput
from app.domains.payroll.service import PayrollService, compute_components

# WS5.1: `read` capability baseline on EVERY route in this router; mutations add
# `write`, approvals add `approve_payment`, statutory filings use the WS5.2 hard gate.
router = APIRouter(
    prefix="/api/payroll",
    tags=["payroll"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = PayrollService()


@router.post("/employees", dependencies=[Depends(require(Capability.WRITE))])
def create_employee(body: NewEmployee, db: Session = Depends(get_session)) -> dict[str, int]:
    # WS10.1 — employee-data ingestion requires the in-force DPDP notice (if any is published)
    # to have been accepted by the verified caller. Same gate as the drawer's add-employee.
    try:
        legal.require_current_acceptance(
            db, current_user(), legal.DocType.DPDP_NOTICE, datetime.now(UTC)
        )
    except legal.ReacceptanceRequiredError as exc:
        # 409, not 403: the caller's ROLE is fine (rbac already passed); the blocking state is
        # a missing acceptance, which the caller can fix and retry.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    emp = Employee(
        employee_code=body.employee_code,
        name=body.name,
        date_of_joining=body.date_of_joining,
        state=body.state,
        pan=body.pan,
        uan=body.uan,
    )
    db.add(emp)
    db.commit()
    return {"id": emp.id}


@router.post("/employees/{employee_id}/salary", dependencies=[Depends(require(Capability.WRITE))])
def set_salary(employee_id: int, body: SalaryInput, db: Session = Depends(get_session)) -> dict:
    try:
        structure = _service.set_salary_structure(
            db,
            employee_id,
            effective_from=body.effective_from,
            basic=body.basic,
            hra=body.hra,
            lta=body.lta,
            special_allowance=body.special_allowance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {
        "structure_id": structure.id,
        "gross_salary": structure.gross_salary,
        "employee_pf": structure.employee_pf,
        "employee_esi": structure.employee_esi,
        "professional_tax": structure.professional_tax,
        "tds_monthly": structure.tds_monthly,
        "net_salary": structure.net_salary,
        "ctc": structure.ctc,
    }


@router.get("/preview", dependencies=[Depends(require_feature("salary_structure"))])
def preview(
    basic: int,
    hra: int,
    lta: int = 0,
    special_allowance: int = 0,
    state: str | None = None,
    month: int = 1,
) -> dict:
    """Compute a salary breakdown without persisting — useful for offer modelling."""
    return compute_components(
        basic=basic,
        hra=hra,
        lta=lta,
        special_allowance=special_allowance,
        state=state,
        month=month,
    )


@router.post(
    "/runs",
    dependencies=[Depends(require(Capability.WRITE)), Depends(require_feature("payroll_run"))],
)
def run(month_year: str, db: Session = Depends(get_session)) -> PayrollRunResult:
    run_date = datetime.now(UTC).date().isoformat()
    result = _service.run_payroll(db, month_year, run_date)
    db.commit()
    return PayrollRunResult(**result)


@router.post("/fold", dependencies=[Depends(require_feature("payroll_run"))])
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
        action="payroll.fold",
    )
    return {
        "snapshot": outcome.snapshot,
        "validation": outcome.fold.validation.model_dump(),
        "shape": outcome.fold.shape.model_dump(),
        "domain_intent": outcome.fold.domain_intent,
        "audit_hash": outcome.audit_hash,
    }


@router.get("/lwf")
def lwf(
    period: str,
    db: Session = Depends(get_session),
    # STATUTORY FILING: "lwf" is in entitlements.STATUTORY_GRACE_FEATURES, so guard() lets a
    # tenant whose plan does NOT include it through (grace) instead of 402-ing. A legal filing
    # is never blocked mid-flow; the upsell is recorded AFTER the fact, in the response below.
    ent: GuardDecision = Depends(require_feature("lwf")),
) -> dict:
    """Labour Welfare Fund due for `period` (state calendars) — thin over the service."""
    return {**_service.lwf_due(db, period=period), "entitlement": entitlement_payload(ent)}
