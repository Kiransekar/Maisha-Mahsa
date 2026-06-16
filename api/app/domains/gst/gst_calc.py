"""GST computation core — pure, exact (integer paise), deterministic.

Covers GSTIN validation (format + check digit), the statutory ITC set-off order
(CGST Act s.49/49A/49B read with Rule 88A), GSTR-3B cash liability, late fee + interest,
and the GSTR-1 outward-supply summary. No clock is read; ``days_late`` is passed in.

Re-verify rates/caps against the current Finance Act (see skills/indian-fin-rules).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# ---- GSTIN validation -----------------------------------------------------------------

_GSTIN_CODES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_digit(first14: str) -> str:
    """The 15th-character check digit for the first 14 GSTIN characters (GSTN algorithm)."""
    mod = len(_GSTIN_CODES)
    factor = 2
    total = 0
    for ch in reversed(first14):
        code = _GSTIN_CODES.index(ch)
        addend = factor * code
        factor = 1 if factor == 2 else 2
        addend = addend // mod + addend % mod
        total += addend
    return _GSTIN_CODES[(mod - total % mod) % mod]


def validate_gstin(gstin: str | None) -> bool:
    """True iff ``gstin`` is structurally valid (incl. state code 01–38) and its check
    digit matches."""
    if not isinstance(gstin, str) or len(gstin) != 15 or not _GSTIN_RE.match(gstin):
        return False
    if not (1 <= int(gstin[:2]) <= 38):
        return False
    return gstin_check_digit(gstin[:14]) == gstin[14]


# ---- ITC set-off ----------------------------------------------------------------------

_HEADS = ("igst", "cgst", "sgst")


def _heads(d: dict[str, int]) -> dict[str, int]:
    return {h: int(d.get(h, 0)) for h in _HEADS}


def itc_setoff(output: dict[str, int], credit: dict[str, int]) -> dict[str, dict[str, int]]:
    """Apply input-tax credit against output tax in the statutory order (Rule 88A):
    IGST credit first (→IGST, →CGST, →SGST), then CGST credit (→CGST, →IGST), then SGST
    credit (→SGST, →IGST). CGST and SGST credit may never cross. Returns the remaining
    cash payable per head and the unutilised credit. All paise."""
    out = _heads(output)
    cr = _heads(credit)

    def apply(src: str, dst: str) -> None:
        amt = min(cr[src], out[dst])
        cr[src] -= amt
        out[dst] -= amt

    apply("igst", "igst")
    apply("igst", "cgst")
    apply("igst", "sgst")
    apply("cgst", "cgst")
    apply("cgst", "igst")
    apply("sgst", "sgst")
    apply("sgst", "igst")

    return {"cash": out, "remaining_credit": cr}


# ---- GSTR-3B --------------------------------------------------------------------------

_LATE_FEE_PER_DAY = 5000  # ₹50/day (CGST ₹25 + SGST ₹25), paise
_LATE_FEE_PER_DAY_NIL = 2000  # ₹20/day for nil returns
_LATE_FEE_CAP = 1_000_000  # ₹10,000 cap
_LATE_FEE_CAP_NIL = 50_000  # ₹500 cap for nil returns
_INTEREST_RATE = Decimal("0.18")  # 18% p.a., s.50


def _round_rupee(paise: int) -> int:
    rupees = (Decimal(int(paise)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rupees) * 100


def late_fee_3b(days_late: int, *, is_nil: bool = False) -> int:
    if days_late <= 0:
        return 0
    per_day = _LATE_FEE_PER_DAY_NIL if is_nil else _LATE_FEE_PER_DAY
    cap = _LATE_FEE_CAP_NIL if is_nil else _LATE_FEE_CAP
    return min(per_day * int(days_late), cap)


def interest_3b(cash_tax: int, days_late: int) -> int:
    if days_late <= 0 or cash_tax <= 0:
        return 0
    interest = Decimal(int(cash_tax)) * _INTEREST_RATE * Decimal(int(days_late)) / Decimal(365)
    return _round_rupee(int(interest.to_integral_value(ROUND_HALF_UP)))


def compute_gstr3b(
    output: dict[str, int],
    itc_available: dict[str, int],
    *,
    days_late: int = 0,
    is_nil: bool = False,
) -> dict[str, Any]:
    """Compute the GSTR-3B cash liability after ITC set-off, plus late fee and interest."""
    setoff = itc_setoff(output, itc_available)
    cash = setoff["cash"]
    cash_total = sum(cash.values())
    fee = late_fee_3b(days_late, is_nil=is_nil)
    interest = interest_3b(cash_total, days_late)
    return {
        "cash": cash,
        "cash_total": cash_total,
        "remaining_credit": setoff["remaining_credit"],
        "late_fee": fee,
        "interest": interest,
        "total_payable": cash_total + fee + interest,
    }


# ---- GSTR-1 outward summary -----------------------------------------------------------


def build_gstr1(lines: list[dict], *, filing_period: str) -> dict[str, Any]:
    """Summarise outward-supply line items into B2B (by buyer GSTIN), B2C (aggregate), and
    an HSN summary. Each line: {invoice_no, gstin?, taxable, igst, cgst, sgst, hsn, qty?}.
    Returns a JSON-able dict plus a list of validation errors (never raises)."""
    errors: list[str] = []
    b2b: dict[str, list[dict]] = {}
    b2c = {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0}
    hsn: dict[str, dict[str, int]] = {}

    for i, ln in enumerate(lines):
        taxes = _heads(ln)
        taxable = int(ln.get("taxable", 0))
        gstin = ln.get("gstin")
        hsn_code = ln.get("hsn")

        if not hsn_code:
            errors.append(f"line {i} ({ln.get('invoice_no', '?')}): missing HSN code")

        if gstin:
            if not validate_gstin(gstin):
                errors.append(f"line {i} ({ln.get('invoice_no', '?')}): invalid GSTIN {gstin}")
            b2b.setdefault(gstin, []).append(
                {"invoice_no": ln.get("invoice_no"), "taxable": taxable, **taxes}
            )
        else:
            b2c["taxable"] += taxable
            for h in _HEADS:
                b2c[h] += taxes[h]

        if hsn_code:
            bucket = hsn.setdefault(
                hsn_code, {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "qty": 0}
            )
            bucket["taxable"] += taxable
            bucket["qty"] += int(ln.get("qty", 0))
            for h in _HEADS:
                bucket[h] += taxes[h]

    totals = {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0}
    for ln in lines:
        totals["taxable"] += int(ln.get("taxable", 0))
        for h in _HEADS:
            totals[h] += int(ln.get(h, 0))
    totals["total_tax"] = totals["igst"] + totals["cgst"] + totals["sgst"]

    return {
        "filing_period": filing_period,
        "b2b": b2b,
        "b2c": b2c,
        "hsn": hsn,
        "totals": totals,
        "errors": errors,
    }
