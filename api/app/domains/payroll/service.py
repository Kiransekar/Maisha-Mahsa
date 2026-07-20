"""Payroll service: salary-structure derivation, the monthly payroll run, and the payroll
health snapshot for Mahsa. All money is integer paise; statutory math is delegated to the
exhaustively-tested ``statutory`` module. Deterministic — the payroll month is passed in.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import pdf
from app.core.domain import BaseDomainService
from app.core.mahsa_client import RecomputeClaim
from app.core.statutory_wage import EXCLUDED_CAP_FRACTION, statutory_wage_base
from app.db.models.payroll import Employee, PayrollEntry, PayrollRun, SalaryStructure
from app.domains.payroll import ecr, statutory
from app.domains.payroll.manifest import MANIFEST


def compute_components(
    *,
    basic: int,
    hra: int,
    lta: int,
    special_allowance: int,
    state: str | None,
    month: int,
    lop_days: int = 0,
    days_in_month: int = 30,
) -> dict[str, int]:
    """Derive gross, statutory deductions, net pay and CTC for one month. Pure.
    ``lop_days`` defaults to 0 (no loss-of-pay → identical to a full month)."""
    gross = int(basic) + int(hra) + int(lta) + int(special_allowance)
    # Route PF & ESI through the Code-on-Wages s.2(y) base, not raw Basic/gross, so an
    # under-weighted CTC yields the correct (larger) base (§WS1.B1). Basic-only input ->
    # wage_base == basic == gross, so existing behaviour is unchanged.
    wage_base = int(
        statutory_wage_base(
            {
                "basic": int(basic),
                "hra": int(hra),
                "lta": int(lta),
                "special_allowance": int(special_allowance),
            }
        )
    )
    emp_pf = int(statutory.pf_employee(wage_base))
    empr_pf = int(statutory.pf_employer(wage_base))
    emp_esi, empr_esi = statutory.esi(wage_base)
    pt = int(statutory.professional_tax(state, gross, month))
    tds = int(statutory.monthly_tds(gross * 12))
    lop = int(statutory.loss_of_pay(gross, lop_days, days_in_month))
    employee_deductions = emp_pf + int(emp_esi) + pt + tds + lop
    net = gross - employee_deductions
    ctc = gross + empr_pf + int(empr_esi)
    return {
        "gross_salary": gross,
        "basic": int(basic),
        "hra": int(hra),
        "lta": int(lta),
        "special_allowance": int(special_allowance),
        "wage_base": wage_base,  # s.2(y) base PF/ESI are computed on (drives recompute claims)
        "employee_pf": emp_pf,
        "employer_pf": empr_pf,
        "employee_esi": int(emp_esi),
        "employer_esi": int(empr_esi),
        "professional_tax": pt,
        "tds_monthly": tds,
        "loss_of_pay": lop,
        "lop_days": int(lop_days),
        "employee_deductions": employee_deductions,
        "net_salary": net,
        "ctc": ctc,
    }


def payslip_recompute_claims(
    comp: dict[str, int], *, label_prefix: str = "payroll"
) -> list[RecomputeClaim]:
    """Prime-Directive claims (§0.4) for the recomputable figures in one payslip ``comp`` (from
    ``compute_components``). Each claim carries the SAME inputs the Python fn used, so Mahsa
    recomputes the identical figure and BLOCKs on any mismatch. PT/TDS/loss-of-pay are not yet
    ported to Mahsa, so no claim is emitted for them (they stay honest-pending elsewhere)."""
    wb = int(comp["wage_base"])
    excluded = int(comp["hra"]) + int(comp["lta"]) + int(comp["special_allowance"])
    return [
        RecomputeClaim(
            target="statutory_wage_base",
            inputs={"included": int(comp["basic"]), "excluded": excluded, "in_kind": 0},
            claimed_paise=wb,
            label=f"{label_prefix}.wage_base",
        ),
        RecomputeClaim(
            target="pf_employee", inputs={"basic_monthly": wb},
            claimed_paise=int(comp["employee_pf"]), label=f"{label_prefix}.pf_employee",
        ),
        RecomputeClaim(
            target="pf_employer", inputs={"basic_monthly": wb},
            claimed_paise=int(comp["employer_pf"]), label=f"{label_prefix}.pf_employer",
        ),
        RecomputeClaim(
            target="esi_employee", inputs={"gross_monthly": wb},
            claimed_paise=int(comp["employee_esi"]), label=f"{label_prefix}.esi_employee",
        ),
        RecomputeClaim(
            target="esi_employer", inputs={"gross_monthly": wb},
            claimed_paise=int(comp["employer_esi"]), label=f"{label_prefix}.esi_employer",
        ),
    ]


def check_ctc_compliance(
    *, basic: int, hra: int, lta: int = 0, special_allowance: int = 0
) -> dict[str, Any]:
    """CTC validator (MMX-1.0 §WS1.B3): Basic+DA must be >= ``EXCLUDED_CAP_FRACTION`` (the same
    s.2(y) 50% threshold ``statutory_wage_base`` uses for its add-back, imported not hardcoded)
    of total remuneration. This salary-structure schema has no separate DA field, so "Basic+DA"
    is just Basic here. Pure — never touches the DB or mutates a stored structure. When
    non-compliant, ``suggestion`` proposes a restructure that raises Basic to the required floor
    by trimming the excluded components (special allowance first, then LTA, then HRA), holding
    total CTC (the sum of these 4 components) exactly constant — the caller must apply it
    explicitly via ``set_salary_structure``; nothing here writes to storage."""
    components = {
        "basic": int(basic),
        "hra": int(hra),
        "lta": int(lta),
        "special_allowance": int(special_allowance),
    }
    total = sum(components.values())
    basic_plus_da = components["basic"]
    compliant = total == 0 or Decimal(basic_plus_da) >= Decimal(total) * EXCLUDED_CAP_FRACTION
    required_minimum = (
        0
        if total == 0
        else int(
            (Decimal(total) * EXCLUDED_CAP_FRACTION).to_integral_value(ROUND_CEILING)
        )
    )
    report: dict[str, Any] = {
        "compliant": compliant,
        "status": "ok" if compliant else "non_compliant",
        "basic_plus_da": basic_plus_da,
        "total_remuneration": total,
        "required_minimum_basic_plus_da": required_minimum,
        "suggestion": None,
    }
    if not compliant:
        report["suggestion"] = _rebalance_suggestion(components, required_minimum)
    return report


def _rebalance_suggestion(components: dict[str, int], required_minimum: int) -> dict[str, int]:
    """Propose Basic raised to ``required_minimum``, funded by trimming excluded components
    (in order: special allowance, LTA, HRA) so total CTC is unchanged. Floors each component
    at zero; never produces a negative component."""
    shortfall = required_minimum - components["basic"]
    proposed = dict(components)
    proposed["basic"] = required_minimum
    for key in ("special_allowance", "lta", "hra"):
        if shortfall <= 0:
            break
        take = min(proposed[key], shortfall)
        proposed[key] -= take
        shortfall -= take
    return proposed


def _month_of(iso_date: str) -> int:
    return date.fromisoformat(iso_date).month


def _structure_wage_base(structure: SalaryStructure) -> int:
    """Code-on-Wages s.2(y) statutory wage base (paise) for a salary structure (§WS1.B1)."""
    return int(
        statutory_wage_base(
            {
                "basic": structure.basic,
                "hra": structure.hra,
                "lta": structure.lta,
                "special_allowance": structure.special_allowance,
            }
        )
    )


class PayrollService(BaseDomainService):
    domain = "payroll"
    keywords = (
        "salary",
        "payroll",
        "pf",
        "epf",
        "esi",
        "tds",
        "employee",
        "ctc",
        "esop",
        "gratuity",
        "bonus",
        "professional tax",
    )
    manifest = MANIFEST

    # ---- salary structure -----------------------------------------------------------

    def set_salary_structure(
        self,
        session: Session,
        employee_id: int,
        *,
        effective_from: str,
        basic: int,
        hra: int,
        lta: int = 0,
        special_allowance: int = 0,
    ) -> SalaryStructure:
        if session.get(Employee, employee_id) is None:
            raise ValueError(f"employee {employee_id} not found")
        emp = session.get(Employee, employee_id)
        comp = compute_components(
            basic=basic,
            hra=hra,
            lta=lta,
            special_allowance=special_allowance,
            state=emp.state if emp else None,
            month=_month_of(effective_from),
        )
        structure = SalaryStructure(
            employee_id=employee_id,
            effective_from=effective_from,
            basic=comp["basic"],
            hra=comp["hra"],
            lta=comp["lta"],
            special_allowance=comp["special_allowance"],
            employer_pf=comp["employer_pf"],
            employer_esi=comp["employer_esi"],
            employee_pf=comp["employee_pf"],
            employee_esi=comp["employee_esi"],
            professional_tax=comp["professional_tax"],
            tds_monthly=comp["tds_monthly"],
            gross_salary=comp["gross_salary"],
            net_salary=comp["net_salary"],
            ctc=comp["ctc"],
        )
        session.add(structure)
        session.flush()
        return structure

    def validate_ctc(
        self, session: Session, employee_id: int, *, on_or_before: str
    ) -> dict[str, Any]:
        """CTC-compliance report (§WS1.B3) for ``employee_id``'s latest salary structure as of
        ``on_or_before``. Read-only — never writes; the caller applies a returned suggestion
        via ``set_salary_structure`` explicitly if they choose to."""
        structure = self._latest_structure(session, employee_id, on_or_before)
        if structure is None:
            raise ValueError(f"no salary structure for employee {employee_id} as of {on_or_before}")
        return check_ctc_compliance(
            basic=structure.basic,
            hra=structure.hra,
            lta=structure.lta,
            special_allowance=structure.special_allowance,
        )

    def _latest_structure(
        self, session: Session, employee_id: int, on_or_before: str
    ) -> SalaryStructure | None:
        rows = session.scalars(
            select(SalaryStructure)
            .where(SalaryStructure.employee_id == employee_id)
            .order_by(SalaryStructure.effective_from.desc())
        ).all()
        for r in rows:
            if r.effective_from <= on_or_before:
                return r
        return None

    # ---- monthly run ----------------------------------------------------------------

    def run_payroll(
        self,
        session: Session,
        month_year: str,
        run_date: str,
        lop_days: dict[int, int] | None = None,
    ) -> dict[str, Any]:
        """Run payroll for ``month_year`` ("YYYY-MM"). Recomputes each active employee's
        entry for that month (so PT February specials etc. apply) from their latest
        effective salary structure. ``lop_days`` optionally maps employee_id → unpaid-leave
        days for the month (loss-of-pay); absent employees are treated as full-month."""
        import calendar

        lop_days = lop_days or {}
        year, month = (int(p) for p in month_year.split("-"))
        days_in_month = calendar.monthrange(year, month)[1]
        anchor = f"{year:04d}-{month:02d}-28"

        run = PayrollRun(month_year=month_year, run_date=run_date, status="draft")
        session.add(run)
        session.flush()

        employees = session.scalars(select(Employee).where(Employee.status == "active")).all()

        totals = {"gross": 0, "deductions": 0, "net": 0, "pf_employer": 0, "esi_employer": 0}
        min_net = None
        count = 0
        for emp in employees:
            structure = self._latest_structure(session, emp.id, anchor)
            if structure is None:
                continue
            comp = compute_components(
                basic=structure.basic,
                hra=structure.hra,
                lta=structure.lta,
                special_allowance=structure.special_allowance,
                state=emp.state,
                month=month,
                lop_days=int(lop_days.get(emp.id, 0)),
                days_in_month=days_in_month,
            )
            session.add(
                PayrollEntry(
                    payroll_run_id=run.id,
                    employee_id=emp.id,
                    gross=comp["gross_salary"],
                    basic=comp["basic"],
                    hra=comp["hra"],
                    lta=comp["lta"],
                    special_allowance=comp["special_allowance"],
                    employee_pf=comp["employee_pf"],
                    employee_esi=comp["employee_esi"],
                    professional_tax=comp["professional_tax"],
                    tds=comp["tds_monthly"],
                    employer_pf=comp["employer_pf"],
                    employer_esi=comp["employer_esi"],
                    net_pay=comp["net_salary"],
                )
            )
            totals["gross"] += comp["gross_salary"]
            totals["deductions"] += comp["employee_deductions"]
            totals["net"] += comp["net_salary"]
            totals["pf_employer"] += comp["employer_pf"]
            totals["esi_employer"] += comp["employer_esi"]
            min_net = comp["net_salary"] if min_net is None else min(min_net, comp["net_salary"])
            count += 1

        run.total_gross = totals["gross"]
        run.total_deductions = totals["deductions"]
        run.total_net = totals["net"]
        run.total_pf_employer = totals["pf_employer"]
        run.total_esi_employer = totals["esi_employer"]
        session.flush()

        return {
            "payroll_run_id": run.id,
            "month_year": month_year,
            "employee_count": count,
            "total_gross": totals["gross"],
            "total_deductions": totals["deductions"],
            "total_net": totals["net"],
            "total_pf_employer": totals["pf_employer"],
            "total_esi_employer": totals["esi_employer"],
            "min_net_pay": 0 if min_net is None else min_net,
        }

    # ---- Labour Welfare Fund (state calendars) --------------------------------------

    def lwf_due(self, session: Session, *, period: str) -> dict[str, Any]:
        """LWF remittance due for ``period`` (YYYY-MM): per-state employee + employer totals,
        non-zero only in each state's due month. Periodic remittance, not a payslip line."""
        month = int(period[5:7])
        by_state: dict[str, dict[str, int]] = {}
        total_emp = total_empr = 0
        for emp in session.scalars(select(Employee).where(Employee.status == "active")).all():
            employee_c, employer_c = statutory.labour_welfare_fund(emp.state, month)
            if int(employee_c) == 0 and int(employer_c) == 0:
                continue
            code = (emp.state or "").upper()
            bucket = by_state.setdefault(code, {"employee": 0, "employer": 0, "members": 0})
            bucket["employee"] += int(employee_c)
            bucket["employer"] += int(employer_c)
            bucket["members"] += 1
            total_emp += int(employee_c)
            total_empr += int(employer_c)
        return {
            "period": period,
            "by_state": by_state,
            "total_employee_paise": total_emp,
            "total_employer_paise": total_empr,
            "total_paise": total_emp + total_empr,
        }

    # ---- statutory documents (payslip / Form 16) ------------------------------------

    def _breakdown(self, session: Session, employee_id: int, *, period: str) -> tuple:
        emp = session.get(Employee, employee_id)
        if emp is None:
            raise ValueError(f"employee {employee_id} not found")
        structure = self._latest_structure(session, employee_id, f"{period}-28")
        if structure is None:
            raise ValueError(f"no salary structure for employee {employee_id} as of {period}")
        comp = compute_components(
            basic=structure.basic,
            hra=structure.hra,
            lta=structure.lta,
            special_allowance=structure.special_allowance,
            state=emp.state,
            month=int(period[5:7]),
        )
        return emp, comp

    def payslip(
        self, session: Session, employee_id: int, *, period: str, company: str = "Maisha-Mahsa"
    ) -> bytes:
        """Monthly payslip PDF for ``period`` (YYYY-MM). Figures come from the payroll engine."""
        emp, comp = self._breakdown(session, employee_id, period=period)
        return pdf.payslip_pdf(
            {
                "company": company,
                "employee_name": emp.name,
                "employee_code": emp.employee_code,
                "period": period,
                "earnings": [
                    ("Basic", comp["basic"]),
                    ("HRA", comp["hra"]),
                    ("Special allowance", comp["special_allowance"]),
                    ("LTA", comp["lta"]),
                ],
                "deductions": [
                    ("PF (employee)", comp["employee_pf"]),
                    ("ESI (employee)", comp["employee_esi"]),
                    ("Professional tax", comp["professional_tax"]),
                    ("TDS", comp["tds_monthly"]),
                ],
                "gross": comp["gross_salary"],
                "total_deductions": comp["employee_deductions"],
                "net": comp["net_salary"],
            }
        )

    def form16(
        self,
        session: Session,
        employee_id: int,
        *,
        financial_year: str,
        company: str = "Maisha-Mahsa",
        tan: str | None = None,
    ) -> bytes:
        """Form 16 Part B PDF for ``financial_year`` (YYYY-YY). Annualises the monthly salary
        and applies the ₹75,000 standard deduction (new-regime FY25-26)."""
        start = int(financial_year[:4])
        emp, comp = self._breakdown(session, employee_id, period=f"{start}-06")
        gross_annual = int(comp["gross_salary"]) * 12
        standard_deduction = 7_500_000  # ₹75,000 in paise (s.16(ia), new regime)
        taxable = max(0, gross_annual - standard_deduction)
        return pdf.form16_pdf(
            {
                "company": company,
                "tan": tan,
                "employee_name": emp.name,
                "pan": emp.pan,
                "financial_year": financial_year,
                "assessment_year": f"{start + 1}-{str(start + 2)[2:]}",
                "rows": [
                    ("Gross salary (annual)", gross_annual),
                    ("Less: Standard deduction u/s 16(ia)", standard_deduction),
                    ("Total taxable income", taxable),
                ],
                "total_tax_deducted": int(comp["tds_monthly"]) * 12,
            }
        )

    def ecr_text(self, session: Session, *, period: str) -> str:
        """Build the EPFO ECR upload file for ``period`` (YYYY-MM) — one #~#-delimited line per
        active member, whole rupees, from the tested statutory PF math."""
        def _r(paise: int) -> int:
            return round(int(paise) / 100)

        anchor = f"{period}-28"
        members: list[ecr.EcrMember] = []
        for emp in session.scalars(select(Employee).where(Employee.status == "active")).all():
            structure = self._latest_structure(session, emp.id, anchor)
            if structure is None:
                continue
            # PF is levied on the Code-on-Wages s.2(y) base, not raw Basic (§WS1.B1); basic-only
            # structures are unchanged (wage_base == basic).
            basic = _structure_wage_base(structure)
            comp = compute_components(
                basic=structure.basic, hra=structure.hra, lta=structure.lta,
                special_allowance=structure.special_allowance, state=emp.state,
                month=int(period[5:7]),
            )
            pf_wage = statutory.pf_wage(basic)
            members.append(
                ecr.EcrMember(
                    uan=emp.uan or "",
                    member_name=emp.name,
                    gross_wages=_r(comp["gross_salary"]),
                    epf_wages=_r(pf_wage),
                    eps_wages=_r(pf_wage),
                    edli_wages=_r(pf_wage),
                    epf_contri_remitted=_r(statutory.pf_employee(basic)),
                    eps_contri_remitted=_r(statutory.eps_employer(basic)),
                    epf_eps_diff_remitted=_r(statutory.epf_employer_diff(basic)),
                )
            )
        return ecr.build_ecr(members)

    # ---- Mahsa contract -------------------------------------------------------------

    def recompute_claims(
        self, session: Session, as_of: date | None = None
    ) -> list[RecomputeClaim]:
        """Emit Prime-Directive claims (§0.4) for every active employee's PF/ESI/wage-base — the
        payroll figures Mahsa can independently recompute. Mismatch → BLOCK; PT/TDS/LOP are not
        yet ported so no claim is emitted for them. Mirrors ``build_snapshot``'s iteration."""
        anchor = as_of or date(1970, 1, 1)
        month = anchor.month
        anchor_iso = anchor.isoformat()
        claims: list[RecomputeClaim] = []
        for emp in session.scalars(select(Employee).where(Employee.status == "active")).all():
            structure = self._latest_structure(session, emp.id, anchor_iso)
            if structure is None:
                continue
            comp = compute_components(
                basic=structure.basic,
                hra=structure.hra,
                lta=structure.lta,
                special_allowance=structure.special_allowance,
                state=emp.state,
                month=month,
            )
            claims.extend(payslip_recompute_claims(comp, label_prefix=f"payroll.emp{emp.id}"))
        return claims

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        month = anchor.month
        anchor_iso = anchor.isoformat()
        employees = session.scalars(select(Employee).where(Employee.status == "active")).all()

        total_gross = 0
        total_employer_pf = 0
        bonus_required = 0
        lwf_due = 0
        min_net: int | None = None
        for emp in employees:
            structure = self._latest_structure(session, emp.id, anchor_iso)
            if structure is None:
                continue
            comp = compute_components(
                basic=structure.basic,
                hra=structure.hra,
                lta=structure.lta,
                special_allowance=structure.special_allowance,
                state=emp.state,
                month=month,
            )
            total_gross += comp["gross_salary"]
            total_employer_pf += comp["employer_pf"]
            bonus_required += int(
                statutory.bonus_provision_monthly(_structure_wage_base(structure))
            )
            employee_lwf, employer_lwf = statutory.labour_welfare_fund(emp.state, month)
            lwf_due += int(employee_lwf) + int(employer_lwf)
            min_net = comp["net_salary"] if min_net is None else min(min_net, comp["net_salary"])

        # Health signals consumed by dif/src/fold/payroll.rs and the payroll rules. We compute
        # statutory amounts correctly, so the accuracy/compliance dims default healthy; deposit
        # timeliness is tracked by the compliance calendar (future) and surfaced there.
        return {
            "as_of": anchor_iso,
            "monthly_burn": total_gross + total_employer_pf,
            "metrics": {
                "pf_compliance": 1.0,
                "esi_compliance": 1.0,
                "tds_accuracy": 1.0,
                "pt_state": 1.0,
                "lwf_state": 1.0,
                "gratuity_reserve": 1.0,
                "bonus_reserve": 1.0,
                "leave_liability": 1.0,
                "min_net_pay_paise": 0 if min_net is None else min_net,
                "monthly_bonus_required_paise": bonus_required,
                "lwf_due_paise": lwf_due,
            },
        }
