"""Expense computation core — pure, exact (integer paise), deterministic.

Covers per-category policy checks, the petty-cash threshold, category analytics, and a
**receipt parser** that extracts structured data from OCR text. The OCR image→text step
(Tesseract, PRD §1.11) is the boundary that's stubbed; this parser works on the text so it
is fully testable.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.core.money import Paise


def reconcile_card(
    statement_lines: list[dict],
    claims: list[dict],
    *,
    date_tolerance_days: int = 3,
    amount_tolerance_paise: int = 0,
) -> dict[str, Any]:
    """Corporate-card reconciliation: greedily match card-statement lines to expense claims by
    amount (within ``amount_tolerance_paise``) and nearest date (within ``date_tolerance_days``).
    Each line/claim: {id?, date 'YYYY-MM-DD', amount_paise}. One-to-one. Pure & deterministic."""
    matched: list[dict] = []
    used_claims: set[int] = set()
    matched_stmt: set[int] = set()
    for si, s in enumerate(statement_lines):
        s_amount = int(s["amount_paise"])
        s_date = date.fromisoformat(s["date"])
        best_ci: int | None = None
        best_gap: int | None = None
        for ci, c in enumerate(claims):
            if ci in used_claims:
                continue
            if abs(int(c["amount_paise"]) - s_amount) > amount_tolerance_paise:
                continue
            gap = abs((date.fromisoformat(c["date"]) - s_date).days)
            if gap <= date_tolerance_days and (best_gap is None or gap < best_gap):
                best_ci, best_gap = ci, gap
        if best_ci is not None:
            used_claims.add(best_ci)
            matched_stmt.add(si)
            matched.append(
                {
                    "statement_id": s.get("id", si),
                    "claim_id": claims[best_ci].get("id", best_ci),
                    "amount_paise": s_amount,
                }
            )
    return {
        "matched": matched,
        "unmatched_statement": [
            s.get("id", i) for i, s in enumerate(statement_lines) if i not in matched_stmt
        ],
        "unmatched_claims": [c.get("id", i) for i, c in enumerate(claims) if i not in used_claims],
        "match_rate": round(len(matched) / len(statement_lines), 4) if statement_lines else 1.0,
    }


# Default per-category reimbursement limits (paise). Override per company in future.
DEFAULT_POLICY: dict[str, int] = {
    "travel": Paise.from_rupees(50000),
    "meals": Paise.from_rupees(2000),
    "supplies": Paise.from_rupees(10000),
    "conveyance": Paise.from_rupees(5000),
}

# PRD §1.11: petty cash imprest threshold.
PETTY_CASH_THRESHOLD = Paise.from_rupees(10000)

_GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
# An amount is either currency-prefixed (₹/Rs/INR ...) OR has a 2-decimal part. This avoids
# matching the bare integers inside a GSTIN or a date.
_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|([0-9][0-9,]*\.[0-9]{2})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})\b")


def check_policy(
    category: str, amount: int, limits: dict[str, int] | None = None
) -> dict[str, Any]:
    """Compare a claim against its category limit. Categories without a limit are unlimited."""
    table = limits if limits is not None else DEFAULT_POLICY
    limit = table.get(category)
    if limit is None:
        return {"over_policy": False, "limit": None, "excess": 0}
    excess = max(0, int(amount) - int(limit))
    return {"over_policy": excess > 0, "limit": int(limit), "excess": excess}


def is_petty_cash_eligible(amount: int) -> bool:
    """True if the amount may be settled from petty cash (≤ ₹10,000)."""
    return int(amount) <= int(PETTY_CASH_THRESHOLD)


def mileage_claim(distance_km: int, *, rate_per_km: int) -> int:
    """Mileage reimbursement = distance × rate-per-km (rate and result in paise)."""
    return int(distance_km) * int(rate_per_km)


def per_diem(days: int, *, rate_per_day: int) -> int:
    """Per-diem travel allowance = days × daily rate (paise)."""
    return int(days) * int(rate_per_day)


def category_spend(claims: list[dict]) -> dict[str, int]:
    """Total claimed amount by category (paise)."""
    totals: dict[str, int] = {}
    for c in claims:
        totals[c["category"]] = totals.get(c["category"], 0) + int(c["amount"])
    return totals


def parse_receipt(ocr_text: str) -> dict[str, Any]:
    """Extract {amount_paise, gstin, date} from OCR text. The amount is the largest money
    figure found (receipts put the total last/largest); paise via Decimal-safe parsing."""
    gstin_match = _GSTIN_RE.search(ocr_text.upper())
    date_match = _DATE_RE.search(ocr_text)

    amounts: list[int] = []
    for currency_grp, decimal_grp in _AMOUNT_RE.findall(ocr_text):
        raw = (currency_grp or decimal_grp).replace(",", "")
        try:
            amounts.append(int(Paise.from_rupees(raw)))
        except Exception:
            continue
    amount_paise = max(amounts) if amounts else None

    return {
        "amount_paise": amount_paise,
        "gstin": gstin_match.group(0) if gstin_match else None,
        "date": date_match.group(0) if date_match else None,
    }
