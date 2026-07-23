"""P0-4 PAYROLL RUN FLOW — preview → typed-confirm over the EXISTING run write, routed into
the EXISTING approvals queue, with the statutory artifacts behind RBAC'd /api download routes.

The three pieces, none of them new machinery:

* ``POST /api/payroll/runs/preview`` (read) — computes the per-employee net/PF/ESI/TDS figures
  the run WOULD write via ``PayrollService.preview_run`` (the SAME loop ``run_payroll`` commits,
  so preview and confirm agree by construction), badges each figure with a LIVE Mahsa recompute
  (§0.4: PF/ESI/wage-base are ported targets and verify to the paisa; TDS/PT/net are not ported
  and honestly read ◐), and mints a confirm token bound to the exact figures shown.
* ``POST /api/payroll/runs/confirm`` (read+write) — typed confirm + token check, then the SAME
  ``run_payroll`` service write ``POST /api/payroll/runs`` performs. The run lands as ``draft``:
  ``build_snapshot``'s ``payroll_run_pending`` metric trips rule PAYROLL-005, the payroll domain
  folds yellow, and the run therefore appears in the EXISTING approvals queue (HTMX and JSON
  alike — ``pending_approvals`` is fold-driven). An approvals decision releases or voids it via
  ``PayrollService.resolve_pending_runs``, called from ``record_decision`` — the one choke point
  every decision surface routes through.
* Artifact downloads — thin /api wrappers over the SAME ``payslip``/``form16``/``ecr_text``
  service methods the HTMX-only ``/d/payroll/*`` routes call, gated on the existing ``export``
  capability (the same gate the audit-pack downloads wear).

Invariants carried in (docs/WS7_BUILD_CONTRACT.md + MASTER_PLAN §0.4/§0.8 + INVARIANT 9):
  · §0.4 — ``verified`` comes only from a live Mahsa recompute that matched; Mahsa down or an
    unported target falls to ``honest_pending``. Nothing here can fabricate a ✓.
  · INVARIANT 9 — no run without preview → typed confirm; the token is recomputed server-side
    at confirm from the CURRENT books, so books that moved since the preview refuse with 409.
  · §0.8 — org for verdict sealing comes from the verified principal only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.entitlement_deps import require_feature
from app.core.landing import mask_field, mask_figures
from app.core.mahsa_client import MahsaClient, MahsaError, RecomputeCheck
from app.core.principal import Principal
from app.core.rbac import Capability, Role, can
from app.core.rbac_deps import require, resolve_principal
from app.core.verdict import Figure, build_verdict
from app.core.verify import verify_claims
from app.db.models.payroll import Employee, PayrollRun
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.payroll.service import PayrollService, payslip_recompute_claims

# Reused, never re-derived: the P0-1 preview/confirm primitives (token seal, badged-figure
# shape, typed-confirm and token checks, audit sealing). One machinery, two flows.
from app.web.api_filings import _check_token, _check_typed, _detail, _figure, _seal, confirm_token

router = APIRouter(
    prefix="/api/payroll",
    tags=["payroll-run"],
    dependencies=[Depends(require(Capability.READ))],
)

_service = PayrollService()

#: What confirming actually does — a draft, not a disbursement. Rendered on every receipt.
QUEUED_NOTE = (
    "The run is drafted, not released: it now sits in Approvals (rule PAYROLL-005), and no "
    "wages are treated as released until an Owner/Admin/Approver approves it there."
)

_WRITE_DENIED = (
    "missing capability: write — running payroll needs a books-writing role "
    "(Owner/Admin/Accountant). You can still read the preview."
)


def _now() -> datetime:
    return datetime.now(UTC)


def _mint_trace(trace_id: str | None) -> str:
    return trace_id or f"payroll-run-{uuid.uuid4().hex[:12]}"


def _fy_of(month_year: str) -> str:
    """Indian financial year (Apr–Mar) containing ``month_year``, as "YYYY-YY"."""
    year, month = (int(p) for p in month_year.split("-"))
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _artifact_links(employees: list[Employee], month_year: str) -> dict[str, Any]:
    fy = _fy_of(month_year)
    return {
        "ecr": f"/api/payroll/ecr.txt?period={month_year}",
        "per_employee": [
            {
                "employee_id": e.id,
                "name": e.name,
                "payslip": f"/api/payroll/employees/{e.id}/payslip.pdf?period={month_year}",
                "form16": f"/api/payroll/employees/{e.id}/form16.pdf?fy={fy}",
            }
            for e in employees
        ],
    }


# ── figures (pure given the checks; exercised via the integration round trips) ───────────

_NOT_PORTED_TDS = "TDS is not yet ported to Mahsa — shown as computed, never dressed up as ✓."
_SUM_NOTE = (
    "A sum of the figures beside it — not an independent recompute target, so it is never "
    "shown ✓; the PF/ESI parts are individually recomputed."
)


def _run_figures(
    rows: list[tuple[Employee, dict[str, int]]],
    checks: dict[str, RecomputeCheck],
    mahsa_up: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(per-employee cards, totals) in the WS7.2 badged-figure shape. ``checks`` is keyed by
    claim LABEL (``payroll.emp{id}.{target}``) — targets repeat across employees, labels don't."""
    employees_out: list[dict[str, Any]] = []
    totals = {"gross": 0, "deductions": 0, "net": 0, "pf_employer": 0, "esi_employer": 0}
    for emp, comp in rows:
        prefix = f"payroll.emp{emp.id}"
        figures = [
            _figure(
                target=f"emp{emp.id}.net_pay",
                label="Net pay",
                value_paise=int(comp["net_salary"]),
                chk=None,
                mahsa_up=mahsa_up,
                formula="gross − (PF + ESI + PT + TDS + loss-of-pay)",
                inputs=[
                    {"label": "gross (paise)", "value": str(comp["gross_salary"])},
                    {"label": "deductions (paise)", "value": str(comp["employee_deductions"])},
                ],
                note=_SUM_NOTE,
            ),
            _figure(
                target=f"emp{emp.id}.pf_employee",
                label="PF (employee)",
                value_paise=int(comp["employee_pf"]),
                chk=checks.get(f"{prefix}.pf_employee"),
                mahsa_up=mahsa_up,
                formula="12% of the s.2(y) statutory wage base (EPF wage ceiling applied)",
                citation="Code on Social Security 2020 s.16(1)(a) (ex EPF & MP Act 1952 s.6)",
                inputs=[{"label": "wage base (paise)", "value": str(comp["wage_base"])}],
            ),
            _figure(
                target=f"emp{emp.id}.esi_employee",
                label="ESI (employee)",
                value_paise=int(comp["employee_esi"]),
                chk=checks.get(f"{prefix}.esi_employee"),
                mahsa_up=mahsa_up,
                formula="employee ESI contribution; nil above the wage ceiling",
                citation="Code on Social Security 2020 s.29 (ex ESI Act 1948 s.39)",
                inputs=[{"label": "wage base (paise)", "value": str(comp["wage_base"])}],
            ),
            _figure(
                target=f"emp{emp.id}.tds",
                label="TDS (monthly)",
                value_paise=int(comp["tds_monthly"]),
                chk=None,
                mahsa_up=mahsa_up,
                note=_NOT_PORTED_TDS,
            ),
        ]
        employees_out.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "name": emp.name,
                "figures": figures,
            }
        )
        totals["gross"] += comp["gross_salary"]
        totals["deductions"] += comp["employee_deductions"]
        totals["net"] += comp["net_salary"]
        totals["pf_employer"] += comp["employer_pf"]
        totals["esi_employer"] += comp["employer_esi"]

    totals_out = [
        _figure(
            target="total_gross",
            label="Total gross",
            value_paise=totals["gross"],
            chk=None,
            mahsa_up=mahsa_up,
            note=_SUM_NOTE,
        ),
        _figure(
            target="total_deductions",
            label="Total employee deductions",
            value_paise=totals["deductions"],
            chk=None,
            mahsa_up=mahsa_up,
            note=_SUM_NOTE,
        ),
        _figure(
            target="total_net",
            label="Total net payable",
            value_paise=totals["net"],
            chk=None,
            mahsa_up=mahsa_up,
            note=_SUM_NOTE,
        ),
        _figure(
            target="total_employer_pf_esi",
            label="Employer PF + ESI on top",
            value_paise=totals["pf_employer"] + totals["esi_employer"],
            chk=None,
            mahsa_up=mahsa_up,
            note=_SUM_NOTE,
        ),
    ]
    return employees_out, totals_out


async def _checked_figures(
    db: Session, mahsa: MahsaClient, month_year: str, org_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, str | None, str | None]:
    """(employees, totals, mahsa_up, rules_version, verdict_hash) for a would-be run — nothing
    written. Mahsa unreachable => every figure honest_pending, stated, never absorbed."""
    rows = _service.preview_run(db, month_year)
    claims = []
    for emp, comp in rows:
        claims.extend(payslip_recompute_claims(comp, label_prefix=f"payroll.emp{emp.id}"))
    checks: dict[str, RecomputeCheck] = {}
    rules_version: str | None = None
    mahsa_up = True
    if claims:
        try:
            fold = await verify_claims(mahsa, claims)
            checks = {c.label: c for c in fold.recompute if c.label}
            rules_version = fold.rules_version
        except MahsaError:
            mahsa_up = False
    employees_out, totals_out = _run_figures(rows, checks, mahsa_up)
    # §0.4: only recomputed-and-matched figures are sealable; nothing verified => no verdict.
    sealed = [
        Figure(key=c.label or c.target, value_paise=int(c.recomputed_paise))
        for c in checks.values()
        if c.matches and c.recomputed_paise is not None
    ]
    verdict_hash = (
        build_verdict(sealed, rules_version, org_id=org_id).hash
        if sealed and rules_version is not None
        else None
    )
    return employees_out, totals_out, mahsa_up, rules_version, verdict_hash


def _flat(employees: list[dict[str, Any]], totals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The figure list the confirm token is minted over — every badged figure, employee cards
    flattened, so a single changed paisa anywhere invalidates the token."""
    return [f for e in employees for f in e["figures"]] + list(totals)


def _masked_employees(role: Role, employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """T11 serialization boundary: per-employee salary figures are masked for roles without
    salary_detail clearance (CA/Approver keep the run's existence and the aggregate totals;
    the per-employee ₹ leaves the body entirely). Applied AFTER confirm-token minting — the
    token seals the real figures; masking is presentation, never the seal."""
    return [{**e, "figures": mask_figures(role, e["figures"])} for e in employees]


# ── routes ───────────────────────────────────────────────────────────────────────────────


@router.get("/runs/overview")
def runs_overview(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Current employees + the last run's status. Stored figures render ◐ (they were verified
    per-employee when previewed; a stored row is not a live recompute)."""
    today = _now().date().isoformat()
    employees = []
    for emp in db.scalars(select(Employee).where(Employee.status == "active")).all():
        structure = _service._latest_structure(db, emp.id, today)
        employees.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "name": emp.name,
                "state_code": emp.state,
                "date_of_joining": emp.date_of_joining,
                # null == "not yet known — we don't guess", never ₹0 (a structure may not
                # exist). T11: masked to {"restricted": true, ...} for roles without
                # salary_detail clearance — the paise never enter the body.
                "monthly_net_paise": mask_field(
                    principal.role,
                    "monthly_net_paise",
                    None if structure is None else int(structure.net_salary),
                ),
                "has_salary_structure": structure is not None,
            }
        )
    last = db.scalars(select(PayrollRun).order_by(PayrollRun.id.desc()).limit(1)).first()
    last_run = None
    if last is not None:
        last_run = {
            "payroll_run_id": last.id,
            "month_year": last.month_year,
            "run_date": last.run_date,
            "status": last.status,
            "figures": [
                _figure(
                    target=key,
                    label=label,
                    value_paise=int(value),
                    chk=None,
                    mahsa_up=True,
                    note="Stored run total — re-verified per employee at the next preview.",
                )
                for key, label, value in (
                    ("last_run_gross", "Total gross", last.total_gross),
                    ("last_run_net", "Total net", last.total_net),
                    ("last_run_deductions", "Total deductions", last.total_deductions),
                )
            ],
            "artifacts": _artifact_links(
                [e for e in db.scalars(select(Employee).where(Employee.status == "active"))],
                last.month_year,
            ),
        }
    pending = db.scalars(select(PayrollRun.id).where(PayrollRun.status == "draft")).all()
    can_run = can(principal.role, Capability.WRITE)
    return {
        "as_of": today,
        "employees": employees,
        "last_run": last_run,
        "runs_pending_approval": len(pending),
        "can_run": can_run,
        "run_denied_reason": None if can_run else _WRITE_DENIED,
    }


class RunPreviewBody(BaseModel):
    month_year: str  # "YYYY-MM"
    trace_id: str | None = None


def _month_or_422(month_year: str) -> None:
    try:
        year, month = (int(p) for p in month_year.split("-"))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"month_year must be YYYY-MM, got {month_year!r}"
        ) from None


@router.post("/runs/preview", dependencies=[Depends(require_feature("payroll_run"))])
async def run_preview(
    body: RunPreviewBody,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Compute + badge the run WITHOUT writing it. No PayrollRun/PayrollEntry row is created
    here — asserted by row-count in the tests (INVARIANT 9)."""
    _month_or_422(body.month_year)
    employees, totals, mahsa_up, rules_version, verdict_hash = await _checked_figures(
        db, mahsa, body.month_year, principal.org_id
    )
    can_confirm = can(principal.role, Capability.WRITE)
    return {
        "kind": "payroll_run",
        "month_year": body.month_year,
        "as_of": _now().date().isoformat(),
        "mahsa_up": mahsa_up,
        "employee_count": len(employees),
        # T11: token first (sealing the REAL figures), then per-employee masking for the body.
        "employees": _masked_employees(principal.role, employees),
        "totals": totals,
        "verdict_hash": verdict_hash,
        "rule_pack_version": rules_version,
        "confirm_phrase": body.month_year,
        "confirm_token": confirm_token(
            "payroll_run", {"month_year": body.month_year}, _flat(employees, totals)
        ),
        "can_confirm": can_confirm,
        "confirm_denied_reason": None if can_confirm else _WRITE_DENIED,
        "will_write": [
            f"A payroll run for {body.month_year} with one entry per employee above, "
            "saved as a DRAFT",
            "An approvals-queue item (rule PAYROLL-005) — the run is not released until an "
            "approver signs it off there",
            "A hash-chained audit entry sealing these figures and this trace id on confirm",
        ],
        "approval_note": QUEUED_NOTE,
        "trace_id": _mint_trace(body.trace_id),
    }


class RunConfirmBody(BaseModel):
    month_year: str
    confirm_token: str
    confirm_text: str
    trace_id: str | None = None


@router.post(
    "/runs/confirm",
    dependencies=[Depends(require(Capability.WRITE)), Depends(require_feature("payroll_run"))],
)
async def run_confirm(
    body: RunConfirmBody,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """The previewed run, committed — via the SAME ``run_payroll`` write the existing
    ``POST /api/payroll/runs`` performs. Figures are recomputed from the CURRENT books and the
    token re-derived: books that moved since the preview refuse with 409, writing nothing."""
    _month_or_422(body.month_year)
    _check_typed(body.confirm_text, body.month_year)
    employees, totals, mahsa_up, rules_version, verdict_hash = await _checked_figures(
        db, mahsa, body.month_year, principal.org_id
    )
    _check_token(
        body.confirm_token,
        confirm_token("payroll_run", {"month_year": body.month_year}, _flat(employees, totals)),
    )
    trace = _mint_trace(body.trace_id)

    result = _service.run_payroll(db, body.month_year, _now().date().isoformat())
    entry = _seal(
        db,
        action="payroll.run_recorded",
        domain="payroll",
        user_id=principal.user_id,
        detail=_detail(
            kind="payroll_run",
            figures=_flat(employees, totals),
            verdict_hash=verdict_hash,
            trace_id=trace,
            month_year=body.month_year,
            payroll_run_id=result["payroll_run_id"],
        ),
        status="recorded",
        rules_version=rules_version,
    )
    db.commit()
    emp_rows = [
        e
        for e in db.scalars(select(Employee).where(Employee.status == "active"))
        if any(x["employee_id"] == e.id for x in employees)
    ]
    return {
        "committed": True,
        "payroll_run_id": result["payroll_run_id"],
        "month_year": body.month_year,
        "status": "draft",
        "employee_count": result["employee_count"],
        # T11 at the boundary here too — a no-op for today's write-holding roles (all cleared
        # for salary_detail), load-bearing the day the two sets diverge.
        "employees": _masked_employees(principal.role, employees),
        "totals": totals,
        "verdict_hash": verdict_hash,
        "mahsa_up": mahsa_up,
        "audit_hash": entry.this_hash,
        "timestamp": entry.timestamp,
        "user_id": principal.user_id,
        "trace_id": trace,
        "approval": {"queued": True, "note": QUEUED_NOTE, "where": "/approvals"},
        "artifacts": _artifact_links(emp_rows, body.month_year),
    }


# ── statutory artifacts (thin /api wrappers over the HTMX-only /d routes' services) ──────


@router.get(
    "/employees/{employee_id}/payslip.pdf",
    dependencies=[Depends(require(Capability.EXPORT))],
)
def payslip_pdf(
    employee_id: int, period: str, db: Session = Depends(get_session)
) -> Response:
    try:
        content = _service.payslip(
            db, employee_id, period=period, company=get_settings().app_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="payslip-{employee_id}-{period}.pdf"'
        },
    )


@router.get(
    "/employees/{employee_id}/form16.pdf",
    dependencies=[Depends(require(Capability.EXPORT))],
)
def form16_pdf(employee_id: int, fy: str, db: Session = Depends(get_session)) -> Response:
    try:
        content = _service.form16(
            db, employee_id, financial_year=fy, company=get_settings().app_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="form16-{employee_id}-{fy}.pdf"'
        },
    )


@router.get("/ecr.txt", dependencies=[Depends(require(Capability.EXPORT))])
def ecr_txt(period: str, db: Session = Depends(get_session)) -> Response:
    text = _service.ecr_text(db, period=period)
    return Response(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="ecr-{period}.txt"'},
    )
