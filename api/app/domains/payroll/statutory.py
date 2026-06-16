"""Indian payroll statutory calculators — pure, exact (integer paise), deterministic.

ALL rates/slabs below are **FY 2025-26 (AY 2026-27), new tax regime** and are declared as
data so they are trivial to update and test. Re-verify against the current Finance Act every
year before relying on these (see skills/indian-fin-rules). No value here is read from a
clock; the caller passes the month where it matters (PT February special).

References: EPF & MP Act 1952 (PF), ESI Act 1948, Income-Tax Act 1961 s.192/87A,
Payment of Bonus Act 1965, Payment of Gratuity Act 1972, state Professional Tax Acts.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.money import Paise

# ---- statutory constants (FY 2025-26) -------------------------------------------------

PF_WAGE_CEILING = Paise.from_rupees(15000)  # monthly PF wage ceiling
PF_RATE = Decimal("0.12")

ESI_WAGE_CEILING = Paise.from_rupees(21000)  # monthly gross; > ceiling => ESI not applicable
ESI_EMPLOYEE_RATE = Decimal("0.0075")
ESI_EMPLOYER_RATE = Decimal("0.0325")

BONUS_ELIGIBILITY_BASIC = Paise.from_rupees(21000)  # Basic+DA monthly
BONUS_WAGE_CAP = Paise.from_rupees(7000)  # calculation ceiling
BONUS_MIN_RATE = Decimal("0.0833")  # 8.33%

GRATUITY_NUM, GRATUITY_DEN = 15, 26  # 15 days' wages per completed year

# New-regime annual slabs: (lower_paise, upper_paise_or_None, rate)
STD_DEDUCTION_ANNUAL = Paise.from_rupees(75000)
REBATE_LIMIT = Paise.from_rupees(1200000)  # s.87A: taxable <= 12L => nil tax
CESS_RATE = Decimal("0.04")
_TDS_SLABS: list[tuple[int, int | None, Decimal]] = [
    (Paise.from_rupees(0), Paise.from_rupees(400000), Decimal("0.00")),
    (Paise.from_rupees(400000), Paise.from_rupees(800000), Decimal("0.05")),
    (Paise.from_rupees(800000), Paise.from_rupees(1200000), Decimal("0.10")),
    (Paise.from_rupees(1200000), Paise.from_rupees(1600000), Decimal("0.15")),
    (Paise.from_rupees(1600000), Paise.from_rupees(2000000), Decimal("0.20")),
    (Paise.from_rupees(2000000), Paise.from_rupees(2400000), Decimal("0.25")),
    (Paise.from_rupees(2400000), None, Decimal("0.30")),
]

# Professional Tax monthly slabs by state. Each entry: (gross_upto_rupees_or_None, paise).
# Only fully-modelled states are listed; unlisted states return 0 (documented limitation).
_PT_TABLES: dict[str, list[tuple[int | None, int]]] = {
    # Maharashtra (men): nil <=7500; 175 up to 10000; 200 above (300 in February).
    "MH": [(7500, 0), (10000, Paise.from_rupees(175)), (None, Paise.from_rupees(200))],
    # Karnataka: nil below 25000; 200 at/above 25000.
    "KA": [(24999, 0), (None, Paise.from_rupees(200))],
}
_PT_STATES_MODELLED = frozenset(_PT_TABLES)


# ---- rounding helpers -----------------------------------------------------------------


def _round_rupee(paise: int) -> int:
    """Round paise to the nearest whole rupee (half up)."""
    rupees = (Decimal(int(paise)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rupees) * 100


def _ceil_rupee(paise: int) -> int:
    """Round paise UP to the next whole rupee (ESI convention)."""
    return -(-int(paise) // 100) * 100


# ---- PF (EPF) -------------------------------------------------------------------------


def pf_wage(basic_monthly: int) -> int:
    """PF wage = Basic (proxy for Basic+DA) capped at the ₹15,000 statutory ceiling."""
    return min(int(basic_monthly), int(PF_WAGE_CEILING))


def pf_employee(basic_monthly: int) -> Paise:
    return Paise(_round_rupee(int(Decimal(pf_wage(basic_monthly)) * PF_RATE)))


def pf_employer(basic_monthly: int) -> Paise:
    # Aggregate employer share 12% (EPS 8.33% on ceiling + EPF 3.67%); modelled as 12% of PF wage.
    return Paise(_round_rupee(int(Decimal(pf_wage(basic_monthly)) * PF_RATE)))


# ---- ESI ------------------------------------------------------------------------------


def esi(gross_monthly: int) -> tuple[Paise, Paise]:
    """(employee, employer) ESI. Nil when gross exceeds the ₹21,000 ceiling."""
    if int(gross_monthly) > int(ESI_WAGE_CEILING):
        return Paise(0), Paise(0)
    emp = _ceil_rupee(int(Decimal(int(gross_monthly)) * ESI_EMPLOYEE_RATE))
    empr = _ceil_rupee(int(Decimal(int(gross_monthly)) * ESI_EMPLOYER_RATE))
    return Paise(emp), Paise(empr)


# ---- Professional Tax -----------------------------------------------------------------


def pt_is_modelled(state: str | None) -> bool:
    return (state or "").upper() in _PT_STATES_MODELLED


def professional_tax(state: str | None, gross_monthly: int, month: int) -> Paise:
    """Monthly PT for a modelled state; ₹0 for unmodelled states. ``month`` is 1-12 (the
    Maharashtra February special of ₹300 depends on it)."""
    code = (state or "").upper()
    table = _PT_TABLES.get(code)
    if table is None:
        return Paise(0)
    gross_rupees = int(gross_monthly) // 100
    amount = 0
    for upto, paise in table:
        if upto is None or gross_rupees <= upto:
            amount = paise
            break
    if code == "MH" and month == 2 and amount == int(Paise.from_rupees(200)):
        amount = int(Paise.from_rupees(300))
    return Paise(amount)


# ---- TDS (Income-Tax s.192, new regime) -----------------------------------------------


def _slab_tax(taxable_annual: int) -> int:
    tax = Decimal(0)
    for lower, upper, rate in _TDS_SLABS:
        if int(taxable_annual) <= lower:
            break
        top = int(taxable_annual) if upper is None else min(int(taxable_annual), upper)
        if top > lower:
            tax += Decimal(top - lower) * rate
    return int(tax)


def annual_income_tax(annual_taxable: int) -> Paise:
    """Annual income tax incl. 4% cess, after s.87A rebate and marginal relief (new regime)."""
    taxable = int(annual_taxable)
    if taxable <= 0:
        return Paise(0)
    base = _slab_tax(taxable)
    if taxable <= int(REBATE_LIMIT):
        base = 0
    else:
        # marginal relief: tax cannot exceed income above the rebate limit.
        excess = taxable - int(REBATE_LIMIT)
        base = min(base, excess)
    with_cess = int((Decimal(base) * (Decimal(1) + CESS_RATE)).to_integral_value(ROUND_HALF_UP))
    return Paise(_round_rupee(with_cess))


def monthly_tds(annual_gross: int) -> Paise:
    """Projected monthly TDS = annual tax on (annual gross − standard deduction) / 12."""
    taxable = max(0, int(annual_gross) - int(STD_DEDUCTION_ANNUAL))
    annual = int(annual_income_tax(taxable))
    return Paise(_round_rupee(round(annual / 12)))


# ---- Gratuity & Bonus provisions ------------------------------------------------------


def gratuity_required(last_basic_monthly: int, completed_years: int) -> Paise:
    """Accrued gratuity liability = (15/26) × last drawn Basic × completed years."""
    if completed_years <= 0:
        return Paise(0)
    amount = Decimal(int(last_basic_monthly)) * GRATUITY_NUM * completed_years / GRATUITY_DEN
    return Paise(_round_rupee(int(amount.to_integral_value(ROUND_HALF_UP))))


def bonus_provision_monthly(basic_monthly: int) -> Paise:
    """Monthly statutory minimum bonus provision (8.33%). Nil if Basic exceeds the
    ₹21,000 eligibility ceiling; calculated on Basic capped at ₹7,000."""
    if int(basic_monthly) > int(BONUS_ELIGIBILITY_BASIC):
        return Paise(0)
    cap = min(int(basic_monthly), int(BONUS_WAGE_CAP))
    return Paise(_round_rupee(int(Decimal(cap) * BONUS_MIN_RATE)))
