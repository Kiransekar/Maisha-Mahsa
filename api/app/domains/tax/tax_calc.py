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
    on the shortfall — assessed tax rounded down to the nearest ₹100 (s.288A) — from 1 Apr of
    the assessment year to the date of payment (``months``)."""
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


def mat_liability(book_profit: int) -> int:
    """Minimum Alternate Tax (s.115JB): 15% of book profit + 4% cess. Surcharge (which
    depends on income slab) is layered on by the caller when applicable."""
    if book_profit <= 0:
        return 0
    base = Decimal(book_profit) * _MAT_RATE
    return _round_rupee(base * (Decimal(1) + _CESS))
