"""Direct-tax computation core — pure, exact (integer paise), deterministic.

Covers the advance-tax schedule + s.234C deferment interest (with the 12%/36% relief
provisos), s.234E TDS-return late fee, the s.44AB tax-audit trigger, and MAT (s.115JB).
Rates/thresholds are **FY 2025-26 (AY 2026-27)** and declared as data — re-verify each
Finance Act (see skills/indian-fin-rules).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.money import Paise

# s.234C installments: (label, cumulative %, relief-floor %, months of interest).
# Q1/Q2 carry the statutory relief (no interest if >=12%/36% paid); Q3/Q4 do not.
_ADVANCE_TAX_SCHEDULE: list[tuple[str, Decimal, Decimal, int]] = [
    ("Q1", Decimal("0.15"), Decimal("0.12"), 3),
    ("Q2", Decimal("0.45"), Decimal("0.36"), 3),
    ("Q3", Decimal("0.75"), Decimal("0.75"), 3),
    ("Q4", Decimal("1.00"), Decimal("1.00"), 1),
]
_MONTHLY_INTEREST = Decimal("0.01")  # 1% per month (s.234B / 234C)

_234E_PER_DAY = Paise.from_rupees(200)

# s.44AB thresholds
_AUDIT_BUSINESS = Paise.from_rupees(10_000_000)  # ₹1 Cr
_AUDIT_BUSINESS_DIGITAL = Paise.from_rupees(100_000_000)  # ₹10 Cr (cash ≤ 5%)
_AUDIT_PROFESSIONAL = Paise.from_rupees(5_000_000)  # ₹50 L

_MAT_RATE = Decimal("0.15")  # s.115JB
_CESS = Decimal("0.04")


def _round_rupee(paise: Decimal) -> int:
    return int((paise / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100


def advance_tax_schedule(total_liability: int) -> list[dict[str, Any]]:
    """Cumulative advance-tax target by installment."""
    return [
        {"installment": label, "cumulative_required": _round_rupee(Decimal(total_liability) * pct)}
        for label, pct, _floor, _m in _ADVANCE_TAX_SCHEDULE
    ]


def interest_234c(total_liability: int, cumulative_paid: list[int]) -> dict[str, Any]:
    """s.234C deferment interest given cumulative advance tax paid by each due date.
    ``cumulative_paid`` is 4 values (by 15 Jun/Sep/Dec/Mar). Relief: no interest for Q1/Q2
    if at least 12%/36% was paid."""
    if len(cumulative_paid) != 4:
        raise ValueError("cumulative_paid must have 4 entries (Q1..Q4)")
    total = 0
    per_installment: dict[str, int] = {}
    for (label, pct, floor_pct, months), paid in zip(
        _ADVANCE_TAX_SCHEDULE, cumulative_paid, strict=True
    ):
        required = Decimal(total_liability) * pct
        floor = Decimal(total_liability) * floor_pct
        if Decimal(paid) >= floor:
            per_installment[label] = 0
            continue
        shortfall = required - Decimal(paid)
        interest = _round_rupee(shortfall * _MONTHLY_INTEREST * months)
        per_installment[label] = interest
        total += interest
    return {"total_234c": total, "by_installment": per_installment}


def interest_234b(assessed_tax: int, advance_paid: int, *, months: int) -> dict[str, Any]:
    """s.234B interest: when advance tax paid is below 90% of assessed tax, 1%/month (simple)
    on the shortfall — the SHORTFALL (the interest base per s.234B(1)) rounded down to the
    nearest ₹100 (Rule 119A(c), Income-tax Rules 1962) — from 1 Apr of the assessment year to
    the date of payment (``months``)."""
    if assessed_tax <= 0 or months <= 0:
        return {"applicable": False, "shortfall": 0, "interest": 0, "months": months}
    if Decimal(advance_paid) >= Decimal(assessed_tax) * Decimal("0.9"):
        return {"applicable": False, "shortfall": 0, "interest": 0, "months": months}
    shortfall = max(0, assessed_tax - advance_paid)
    shortfall = (shortfall // 10000) * 10000  # round down to nearest ₹100 (10,000 paise)
    interest = _round_rupee(Decimal(shortfall) * _MONTHLY_INTEREST * months)
    return {"applicable": True, "shortfall": shortfall, "interest": interest, "months": months}


def late_fee_234e(days_late: int, tds_amount: int) -> int:
    """s.234E late fee for a TDS return: ₹200/day, capped at the TDS amount."""
    if days_late <= 0:
        return 0
    return min(int(_234E_PER_DAY) * int(days_late), int(tds_amount))


def tax_holiday_deduction(profit: int, *, claimed_years: int, eligible: bool) -> dict[str, Any]:
    """s.80-IAC: an eligible DPIIT-recognised startup may deduct 100% of profits for any 3
    consecutive AYs out of its first 10. ``claimed_years`` is how many of the 3 are already
    used. Grants the deduction this year only if eligible, profit is positive, and the 3-year
    allowance isn't exhausted."""
    available = eligible and profit > 0 and claimed_years < 3
    deduction = int(profit) if available else 0
    return {
        "eligible": available,
        "deduction": deduction,
        "taxable_after_holiday": int(profit) - deduction,
        "holiday_years_remaining": max(0, 3 - claimed_years - (1 if available else 0)),
    }


def reconcile_26as(books: list[dict], as_26as: list[dict]) -> dict[str, Any]:
    """Reconcile TDS credits in the books against Form 26AS (the department's record). Entries
    are aggregated by deductor TAN: {tan, amount}. Flags mismatches and one-sided entries."""
    book_by_tan: dict[str, int] = {}
    dept_by_tan: dict[str, int] = {}
    for e in books:
        book_by_tan[e["tan"]] = book_by_tan.get(e["tan"], 0) + int(e["amount"])
    for e in as_26as:
        dept_by_tan[e["tan"]] = dept_by_tan.get(e["tan"], 0) + int(e["amount"])

    matched: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []
    missing_in_26as: list[dict[str, Any]] = []
    missing_in_books: list[dict[str, Any]] = []
    for tan in sorted(set(book_by_tan) | set(dept_by_tan)):
        bv, dv = book_by_tan.get(tan), dept_by_tan.get(tan)
        if dv is None:
            missing_in_26as.append({"tan": tan, "books": bv})
        elif bv is None:
            missing_in_books.append({"tan": tan, "as_26as": dv})
        elif bv == dv:
            matched.append({"tan": tan, "amount": bv})
        else:
            mismatched.append({"tan": tan, "books": bv, "as_26as": dv, "variance": bv - dv})
    return {
        "matched": matched,
        "mismatched": mismatched,
        "missing_in_26as": missing_in_26as,
        "missing_in_books": missing_in_books,
        "reconciled": not (mismatched or missing_in_26as or missing_in_books),
    }


def audit_required(
    turnover: int, *, cash_ratio: float = 0.0, is_professional: bool = False
) -> bool:
    """s.44AB tax-audit trigger. Business: > ₹10 Cr always; > ₹1 Cr if cash receipts/payments
    exceed 5%. Profession: gross receipts > ₹50 L."""
    if is_professional:
        return turnover > int(_AUDIT_PROFESSIONAL)
    if turnover > int(_AUDIT_BUSINESS_DIGITAL):
        return True
    return turnover > int(_AUDIT_BUSINESS) and cash_ratio > 0.05


# s.115BAA concessional regime (companies): 22% base + 10% surcharge + 4% cess = 25.168%
# effective (MMX-1.0 §WS1.C4). MAT (s.115JB) does NOT apply on this path.
_COMPANY_115BAA_BASE = Decimal("0.22")
_COMPANY_115BAA_SURCHARGE = Decimal("0.10")
_FIRM_TAX_RATE = Decimal("0.30")  # LLP / firm
_ONE_CRORE_PAISE = 10**7 * 100
_RULE_10D_THRESHOLD = _ONE_CRORE_PAISE  # Rs 1 crore aggregate international transactions
_MASTER_FILE_THRESHOLD = 500 * _ONE_CRORE_PAISE  # Rs 500 crore group revenue
_CBCR_THRESHOLD = 5500 * _ONE_CRORE_PAISE  # Rs 5500 crore group revenue (s.286)


def itr_computation(
    *,
    entity_type: str,
    gross_total_income: int,
    deductions: int = 0,
    book_profit: int | None = None,
    tds_paid: int = 0,
    advance_tax_paid: int = 0,
    regime_115baa: bool = True,
) -> dict[str, Any]:
    """Prepare the headline ITR computation. ``entity_type`` 'company' → ITR-6, 'firm'/'llp' →
    ITR-5 (30% + cess). The company regime is chosen explicitly (§WS1.C4): ``regime_115baa=True``
    (default) → 22% + 10% surcharge + 4% cess = 25.168% effective, and MAT (s.115JB) is EXCLUDED;
    the non-115BAA path (normal rates + MAT comparison) has no CA-initialled rate vector yet and is
    BLOCKED-CA. Prepaid TDS + advance tax are netted off. The e-filing upload is out of scope.
    Pure & exact paise."""
    et = entity_type.lower()
    total_income = max(0, int(gross_total_income) - int(deductions))
    if et == "company":
        if not regime_115baa:
            raise NotImplementedError(
                "BLOCKED-CA: non-115BAA company tax needs a CA-initialled rate vector "
                "(MMX-1.0 §0.6, §WS1.C4)."
            )
        form = "ITR-6"
        # 22% × 1.10 surcharge × 1.04 cess = 25.168% effective; MAT excluded on this path.
        effective = (
            _COMPANY_115BAA_BASE * (Decimal(1) + _COMPANY_115BAA_SURCHARGE) * (Decimal(1) + _CESS)
        )
        normal_tax = _round_rupee(Decimal(total_income) * effective)
        mat = 0
    else:
        form = "ITR-5"
        normal_tax = _round_rupee(Decimal(total_income) * _FIRM_TAX_RATE * (Decimal(1) + _CESS))
        mat = 0
    tax_payable = max(normal_tax, mat)
    prepaid = int(tds_paid) + int(advance_tax_paid)
    return {
        "form": form,
        "entity_type": et,
        "total_income": total_income,
        "normal_tax": normal_tax,
        "mat": mat,
        "tax_payable": tax_payable,
        "prepaid_taxes": prepaid,
        "balance_payable": max(0, tax_payable - prepaid),
        "refund_due": max(0, prepaid - tax_payable),
    }


def arms_length_check(
    price: int, comparables: list[int], *, tolerance_pct: float = 3.0
) -> dict[str, Any]:
    """Arm's-length test for a controlled transaction. The arm's-length price is the arithmetic
    mean of the uncontrolled comparables (Rule 10CA); a ±``tolerance_pct`` band (3% proviso)
    defines the acceptable range. Returns whether ``price`` is at arm's length and any TP
    adjustment to the ALP. Pure."""
    if not comparables:
        return {"at_arms_length": None, "reason": "no comparables provided"}
    mean = sum(int(c) for c in comparables) // len(comparables)
    band = int(
        (Decimal(mean) * Decimal(str(tolerance_pct)) / Decimal(100)).to_integral_value(
            ROUND_HALF_UP
        )
    )
    lower, upper = mean - band, mean + band
    at_arms_length = lower <= int(price) <= upper
    return {
        "at_arms_length": at_arms_length,
        "arms_length_price": mean,
        "lower": lower,
        "upper": upper,
        "adjustment": 0 if at_arms_length else mean - int(price),
    }


def tp_documentation_required(
    *, intl_transaction_value: int, group_consolidated_revenue: int = 0
) -> dict[str, Any]:
    """Transfer-pricing documentation thresholds: Form 3CEB whenever international transactions
    exist; Rule 10D documentation if their aggregate value exceeds ₹1 crore; Master File if group
    consolidated revenue exceeds ₹500 crore; CbCR (s.286) above ₹5,500 crore. Money in paise."""
    intl = int(intl_transaction_value)
    group = int(group_consolidated_revenue)
    return {
        "form_3ceb_required": intl > 0,
        "rule_10d_documentation": intl > _RULE_10D_THRESHOLD,
        "master_file_required": group > _MASTER_FILE_THRESHOLD,
        "cbcr_required": group > _CBCR_THRESHOLD,
    }


def mat_liability(book_profit: int) -> int:
    """Minimum Alternate Tax (s.115JB): 15% of book profit + 4% cess. Surcharge (which
    depends on income slab) is layered on by the caller when applicable."""
    if book_profit <= 0:
        return 0
    base = Decimal(book_profit) * _MAT_RATE
    return _round_rupee(base * (Decimal(1) + _CESS))
