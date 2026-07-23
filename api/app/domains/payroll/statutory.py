"""Indian payroll statutory calculators — pure, exact (integer paise), deterministic.

ALL rates/slabs below are **FY 2025-26 (AY 2026-27), new tax regime** and are declared as
data so they are trivial to update and test. Re-verify against the current Finance Act every
year before relying on these (see skills/indian-fin-rules). No value here is read from a
clock; the caller passes the month where it matters (PT February special).

References (Labour-Code regime in force 21-11-2025; repealed Acts appear only as "(ex ...)"
traces per the WS1.B4 convention): Code on Social Security 2020 s.16(1)(a) (PF, ex EPF & MP Act
1952), s.29 (ESI, ex ESI Act 1948), s.53 (gratuity, ex Payment of Gratuity Act 1972);
Code on Wages 2019 s.26 (bonus, ex Payment of Bonus Act 1965) and s.2(y) (wage base);
Income-Tax Act 1961 s.192/87A; state Professional Tax Acts.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.core import state_packs
from app.core.money import Paise

# ---- statutory constants (FY 2025-26) -------------------------------------------------

PF_WAGE_CEILING = Paise.from_rupees(15000)  # monthly PF wage ceiling
PF_RATE = Decimal("0.12")
EPS_RATE = Decimal("0.0833")  # employer EPS share (8.33% of EPS wage)

ESI_WAGE_CEILING = Paise.from_rupees(21000)  # monthly gross; > ceiling => ESI not applicable
ESI_EMPLOYEE_RATE = Decimal("0.0075")
ESI_EMPLOYER_RATE = Decimal("0.0325")

BONUS_ELIGIBILITY_BASIC = Paise.from_rupees(21000)  # Basic+DA monthly
BONUS_WAGE_CAP = Paise.from_rupees(7000)  # calculation ceiling
# CoW 2019 s.26(1) verbatim: minimum bonus "at the rate of eight and one-third per cent. of the
# wages earned by the employee or one hundred rupees, whichever is higher". 8-1/3% is EXACTLY
# 1/12 — kept as an integer fraction, never a decimal approximation (the old 0.0833 was a
# WS1.E2 D1 defect: Basic ₹6,006 gave ₹500 instead of the statutory ₹501).
BONUS_MIN_RATE_NUM, BONUS_MIN_RATE_DEN = 1, 12
BONUS_ANNUAL_FLOOR = Paise.from_rupees(100)  # s.26(1) "one hundred rupees" (annual)

GRATUITY_NUM, GRATUITY_DEN = 15, 26  # 15 days' wages per completed year
# CoSS 2020 s.53(1): "Gratuity shall be payable to an employee on the termination of his
# employment after he has rendered continuous service for not less than five years"; second
# proviso: "the completion of continuous service of five years shall not be necessary where the
# termination ... is due to death or disablement or expiration of fixed term employment".
# The FTE floor of one year is MoLE Additional FAQs on Labour Codes (16.03.2026) Sl.14/19.
GRATUITY_MIN_YEARS = 5
GRATUITY_MIN_YEARS_FIXED_TERM = 1
# CoSS 2020 s.53(3): "The amount of gratuity payable to an employee shall not exceed such amount
# as may be notified by the Central Government." Amount applied: ₹20,00,000 — S.O. 1420(E)
# 29-03-2018 (notified under PoG Act 1972 s.4(3)), carried into s.53(3) by CoSS s.164(2)(a)
# (repealed-Act notifications "deemed to have been done ... under the corresponding provisions
# of this Code"). No CoSS-specific s.53(3) notification could be sourced; see the ceiling
# vectors in ws1b_wiring_gratuity.yaml (provenance=interpretation, ca_initials OWNER).
GRATUITY_CEILING = Paise.from_rupees(2000000)

# New-regime annual slabs: (lower_paise, upper_paise_or_None, rate)
STD_DEDUCTION_ANNUAL = Paise.from_rupees(75000)
REBATE_LIMIT = Paise.from_rupees(1200000)  # s.87A: taxable <= 12L => nil tax
# Health & Education Cess: 4% of income-tax and surcharge (FA 2025 s.2(11)) — applied as the
# exact ×104/100 integer step inside annual_income_tax, no Decimal rate constant needed.
_TDS_SLABS: list[tuple[int, int | None, Decimal]] = [
    (Paise.from_rupees(0), Paise.from_rupees(400000), Decimal("0.00")),
    (Paise.from_rupees(400000), Paise.from_rupees(800000), Decimal("0.05")),
    (Paise.from_rupees(800000), Paise.from_rupees(1200000), Decimal("0.10")),
    (Paise.from_rupees(1200000), Paise.from_rupees(1600000), Decimal("0.15")),
    (Paise.from_rupees(1600000), Paise.from_rupees(2000000), Decimal("0.20")),
    (Paise.from_rupees(2000000), Paise.from_rupees(2400000), Decimal("0.25")),
    (Paise.from_rupees(2400000), None, Decimal("0.30")),
]

# Individual surcharge, new regime (FA 2025 s.2(9), provisos for income chargeable under
# s.115BAC(1A), read verbatim 2026-07-23): 10% where total income exceeds ₹50L but does not
# exceed ₹1cr; 15% above ₹1cr up to ₹2cr; 25% above ₹2cr. The new-regime proviso has NO 37%
# band — 25% is its highest rate. Marginal relief (next proviso, same source): tax+surcharge
# shall not exceed tax(+surcharge) on the band's lower threshold plus the income in excess of
# that threshold. This engine projects salary income only; the 15% surcharge ceiling for
# dividend/s.111A/112/112A income (bands (iv)/proviso) is out of scope.
# (lower_threshold_paise, surcharge_rate_percent) — a band applies when taxable > lower.
_SURCHARGE_BANDS: list[tuple[int, int]] = [
    (Paise.from_rupees(5000000), 10),
    (Paise.from_rupees(10000000), 15),
    (Paise.from_rupees(20000000), 25),
]

# Professional Tax comes from the WS2 state packs (app/states/<code>.yaml — cited, sha256-
# verified data; see app/core/state_packs.py). The old in-code _PT_TABLES were deleted when
# the packs shipped: an uncited in-code slab cannot satisfy §0.6, and KA's table was in fact
# stale (missed the Rs.300 February rate, Act 33 of 2025 w.e.f. 01.04.2025).

# Labour Welfare Fund: (employee_paise, employer_paise, due_months). LWF is a PERIODIC
# remittance (half-yearly/annual), NOT a monthly payslip line — surfaced as a compliance
# figure, returned only in its due month(s). Amounts/calendars vary by state and change;
# re-verify against each state's LWF Act/notification annually.
_LWF_TABLES: dict[str, tuple[int, int, tuple[int, ...]]] = {
    "MH": (Paise.from_rupees(25), Paise.from_rupees(75), (6, 12)),  # half-yearly: Jun, Dec
    "KA": (Paise.from_rupees(20), Paise.from_rupees(40), (12,)),  # annual: Dec
    "TN": (Paise.from_rupees(20), Paise.from_rupees(40), (12,)),  # annual: Dec
    "GJ": (Paise.from_rupees(6), Paise.from_rupees(12), (6, 12)),  # half-yearly
    "WB": (Paise.from_rupees(3), Paise.from_rupees(15), (6, 12)),  # half-yearly
    "AP": (Paise.from_rupees(30), Paise.from_rupees(70), (12,)),  # annual
    "MP": (Paise.from_rupees(10), Paise.from_rupees(30), (6, 12)),  # half-yearly
}
_LWF_STATES_MODELLED = frozenset(_LWF_TABLES)


# ---- rounding helpers -----------------------------------------------------------------


def _round_rupee(paise: Decimal | int) -> int:
    """Round to the nearest whole rupee (half up). Accepts an EXACT Decimal paise amount —
    callers must not pre-truncate with int() (that is the §WS1.C3 truncate-then-round defect)."""
    rupees = (Decimal(paise) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rupees) * 100


def _ceil_rupee(paise: Decimal | int) -> int:
    """Round UP to the next whole rupee (ESI convention). Ceil is applied to the EXACT Decimal
    product BEFORE any int truncation, so a fractional-paise remainder still rounds up (§WS1.C3)."""
    rupees = (Decimal(paise) / 100).quantize(Decimal("1"), rounding=ROUND_CEILING)
    return int(rupees) * 100


# ---- PF (EPF) -------------------------------------------------------------------------


def pf_wage(basic_monthly: int) -> int:
    """PF wage = Basic (proxy for Basic+DA) capped at the ₹15,000 statutory ceiling."""
    return min(int(basic_monthly), int(PF_WAGE_CEILING))


def pf_employee(basic_monthly: int) -> Paise:
    return Paise(_round_rupee(Decimal(pf_wage(basic_monthly)) * PF_RATE))


def pf_employer(basic_monthly: int) -> Paise:
    # Aggregate employer share 12% (EPS 8.33% on ceiling + EPF 3.67%); modelled as 12% of PF wage.
    return Paise(_round_rupee(Decimal(pf_wage(basic_monthly)) * PF_RATE))


def eps_employer(basic_monthly: int) -> Paise:
    """Employer's EPS share = 8.33% of EPS wage (PF wage capped at ₹15,000 → max ₹1,250)."""
    return Paise(_round_rupee(Decimal(pf_wage(basic_monthly)) * EPS_RATE))


def epf_employer_diff(basic_monthly: int) -> Paise:
    """Employer's EPF share = total employer 12% − EPS 8.33% (the 3.67% remitted to EPF)."""
    return Paise(int(pf_employer(basic_monthly)) - int(eps_employer(basic_monthly)))


# ---- ESI ------------------------------------------------------------------------------


def esi(gross_monthly: int) -> tuple[Paise, Paise]:
    """(employee, employer) ESI. Nil when gross exceeds the ₹21,000 ceiling."""
    if int(gross_monthly) > int(ESI_WAGE_CEILING):
        return Paise(0), Paise(0)
    emp = _ceil_rupee(Decimal(int(gross_monthly)) * ESI_EMPLOYEE_RATE)
    empr = _ceil_rupee(Decimal(int(gross_monthly)) * ESI_EMPLOYER_RATE)
    return Paise(emp), Paise(empr)


# ---- Professional Tax -----------------------------------------------------------------


def pt_is_modelled(state: str | None) -> bool:
    """True when the state's pack computes a MONTHLY payslip PT line (sourced monthly slabs)."""
    return state_packs.pt_status(state) == "monthly"


def professional_tax(state: str | None, gross_monthly: int, month: int) -> Paise:
    """Monthly-payslip PT via the WS2 state pack. ``month`` is 1-12 (February specials —
    MH ₹300, and KA ₹300 w.e.f. 01.04.2025 — come from the cited pack data).

    The payslip line is ₹0 in three HONEST cases the pack distinguishes (surfaced via
    ``state_packs.pt_provenance`` — the zero is never "computed as zero"):
      * ``not_applicable`` — no PT levy exists in the state (DL/HR/UP);
      * ``half_yearly``    — the levy is half-yearly per local body (TN), computed via
        ``state_packs.pt_half_yearly``, not as a monthly deduction;
      * ``no_pack``        — state not yet covered (WS2.4 backlog; pre-pack behaviour).
    A BLOCKED-CA pack refuses (raises) rather than returning zero (§0.6).
    """
    det = state_packs.pt_monthly(state, gross_monthly, month)
    return Paise(det.amount_paise if det.amount_paise is not None else 0)


# ---- Labour Welfare Fund (state calendars) --------------------------------------------


def lwf_is_modelled(state: str | None) -> bool:
    return (state or "").upper() in _LWF_STATES_MODELLED


def labour_welfare_fund(state: str | None, month: int) -> tuple[Paise, Paise]:
    """(employee, employer) LWF contribution for ``month`` (1-12). Non-zero only in the
    state's due month(s); ₹0 for unmodelled states or non-due months."""
    entry = _LWF_TABLES.get((state or "").upper())
    if entry is None:
        return Paise(0), Paise(0)
    employee, employer, due_months = entry
    if int(month) in due_months:
        return Paise(employee), Paise(employer)
    return Paise(0), Paise(0)


# ---- Leave & attendance (loss-of-pay) -------------------------------------------------


def loss_of_pay(monthly_amount: int, lop_days: int, days_in_month: int = 30) -> Paise:
    """Loss-of-pay deduction = monthly_amount × lop_days / days_in_month (capped at the
    month). ₹0 when there are no unpaid-leave days. Pure, exact paise."""
    if int(lop_days) <= 0:
        return Paise(0)
    days = max(1, int(days_in_month))
    lop = min(int(lop_days), days)
    value = Decimal(int(monthly_amount)) * lop / days
    return Paise(_round_rupee(int(value.to_integral_value(ROUND_HALF_UP))))


def leave_balance(opening_days: float, accrued_days: float, taken_days: float) -> float:
    """Closing leave balance = opening + accrued − taken, floored at zero."""
    return max(0.0, float(opening_days) + float(accrued_days) - float(taken_days))


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


def _tax_with_surcharge_hundredths(taxable: int) -> int:
    """Slab tax + surcharge in HUNDREDTHS of a paisa — exact integers throughout (surcharge
    percentages make the exact value a multiple of 1/100 paisa). Applies the FA 2025 s.2(9)
    new-regime bands and their marginal relief: tax+surcharge on ``taxable`` may not exceed
    tax+surcharge on the band's lower threshold plus the income above that threshold."""
    base_h = _slab_tax(taxable) * 100
    band = None
    for lower, rate in _SURCHARGE_BANDS:
        if taxable > lower:
            band = (lower, rate)
    if band is None:
        return base_h
    lower, rate = band
    with_surcharge = _slab_tax(taxable) * (100 + rate)
    relief_cap = _tax_with_surcharge_hundredths(lower) + (taxable - lower) * 100
    return min(with_surcharge, relief_cap)


def annual_income_tax(annual_taxable: int) -> Paise:
    """Annual income tax incl. surcharge (>₹50L bands, FA 2025 s.2(9)) and 4% cess, after the
    s.87A rebate and its marginal relief (new regime). Exact integer arithmetic end to end."""
    taxable = int(annual_taxable)
    if taxable <= 0:
        return Paise(0)
    if taxable <= int(REBATE_LIMIT):
        tax_h = 0
    else:
        tax_h = _tax_with_surcharge_hundredths(taxable)
        # s.87A marginal relief: tax cannot exceed income above the rebate limit (can only
        # bind just above ₹12L, far below the surcharge bands).
        tax_h = min(tax_h, (taxable - int(REBATE_LIMIT)) * 100)
    # 4% cess on tax+surcharge (FA 2025 s.2(11)), half-up to the paisa, then to the rupee —
    # (tax_h × 104) / 10000 paise exactly; identical to the pre-surcharge two-step rounding.
    with_cess = (tax_h * 104 + 5000) // 10000
    return Paise(_round_rupee(with_cess))


def monthly_tds(annual_gross: int) -> Paise:
    """Projected monthly TDS = annual tax on (annual gross − standard deduction) / 12."""
    taxable = max(0, int(annual_gross) - int(STD_DEDUCTION_ANNUAL))
    annual = int(annual_income_tax(taxable))
    return Paise(_round_rupee(round(annual / 12)))


# ---- Gratuity & Bonus provisions ------------------------------------------------------


def gratuity_required(last_basic_monthly: int, completed_years: int) -> Paise:
    """Accrued gratuity liability = (15/26) × last drawn Basic × completed years, capped at the
    s.53(3) notified ceiling (₹20 lakh) — the payable amount can never exceed the cap."""
    if completed_years <= 0:
        return Paise(0)
    amount = Decimal(int(last_basic_monthly)) * GRATUITY_NUM * completed_years / GRATUITY_DEN
    return Paise(
        min(_round_rupee(int(amount.to_integral_value(ROUND_HALF_UP))), int(GRATUITY_CEILING))
    )


def _completed_years(start: date, end: date) -> int:
    """Whole completed years of service from ``start`` through ``end`` (anniversary count)."""
    if end < start:
        return 0
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return max(0, years)


def gratuity_hybrid(
    *,
    doj: date,
    exit_date: date,
    boundary: date,
    old_base: int,
    new_base: int,
    fixed_term: bool = False,
) -> Paise:
    """Hybrid gratuity across the Labour-Code transition (MMX-1.0 §WS1.B2).

    Completed years of service rendered before ``boundary`` (21-11-2025) are valued on the OLD
    base (last-drawn Basic); years completed on/after ``boundary`` on the NEW s.2(y) wage base.
    Both legs reuse the same 15/26 factor; the legs are summed and rounded once, then capped at
    the s.53(3) notified ceiling (₹20 lakh). All dates are injected — no clock. ``old_base`` and
    ``new_base`` are the monthly Basic / statutory wage base in paise.

    Eligibility (CoSS 2020 s.53(1)): continuous service of not less than FIVE years, except that
    for fixed-term employment (``fixed_term=True``) the second proviso disapplies the five-year
    requirement and the MoLE FAQ fixes the FTE floor at one year (defect #3, fixed — the old
    code applied the 1-year FTE exception to every employee).

    Apportionment (a computational interpretation, no statutory value invented): a completed year
    is assigned to the pre-boundary leg when its anniversary (completion date) falls strictly
    before ``boundary``, else to the post-boundary leg.
    """
    total_years = _completed_years(doj, exit_date)
    floor = GRATUITY_MIN_YEARS_FIXED_TERM if fixed_term else GRATUITY_MIN_YEARS
    if total_years < floor:
        return Paise(0)
    b = (boundary.year, boundary.month, boundary.day)
    pre_years = sum(1 for k in range(1, total_years + 1) if (doj.year + k, doj.month, doj.day) < b)
    post_years = total_years - pre_years
    old_leg = Decimal(int(old_base)) * GRATUITY_NUM * pre_years / GRATUITY_DEN
    new_leg = Decimal(int(new_base)) * GRATUITY_NUM * post_years / GRATUITY_DEN
    total = old_leg + new_leg
    return Paise(
        min(_round_rupee(int(total.to_integral_value(ROUND_HALF_UP))), int(GRATUITY_CEILING))
    )


def bonus_provision_monthly(basic_monthly: int) -> Paise:
    """Monthly statutory minimum bonus provision (CoW 2019 s.26(1): 8-1/3% = exactly 1/12, or
    ₹100/year, whichever is higher). Nil if Basic exceeds the ₹21,000 eligibility ceiling;
    calculated on Basic capped at ₹7,000.

    The s.26(1) floor is an ANNUAL ₹100. On a constant capped monthly wage the annual minimum
    at 1/12 equals exactly ONE month's capped wage, so the annual minimum = max(cap, ₹100) and
    this monthly accrual slice = max(cap, ₹100) / 12 — exact integer paise, half-up to the
    whole rupee (module convention). Pure integer arithmetic: no float, no Decimal rate.
    """
    if int(basic_monthly) > int(BONUS_ELIGIBILITY_BASIC):
        return Paise(0)
    cap = min(int(basic_monthly), int(BONUS_WAGE_CAP))
    annual = max(cap * BONUS_MIN_RATE_NUM, int(BONUS_ANNUAL_FLOOR))
    # exact rupees = annual / (12 × 100); half-up: floor(x + 1/2) = (annual + 600) // 1200
    return Paise(((annual + 600) // 1200) * 100)
