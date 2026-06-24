"""Payables computation core — pure, exact (integer paise), deterministic.

Covers the TDS-on-payments section engine (194C/194J/194H/194I) with rates + thresholds,
the PO↔GRN↔invoice 3-way match, AP aging, and the MSMED 45-day clock. TDS is computed on
the taxable value (excluding GST, per CBDT Circular 23/2017). Time is injected via ``as_of``.

Rates/thresholds are **FY 2025-26** and declared as data — re-verify each Finance Act
(see skills/indian-fin-rules).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# section -> config. `single` = per-transaction threshold; `aggregate` = annual threshold
# (TDS applies if either is crossed). Rates in percent.
_TDS_SECTIONS: dict[str, dict[str, Any]] = {
    # 194C: contractors — 1% (individual/HUF) else 2%; single ₹30k, aggregate ₹1L.
    "194C": {
        "rate_individual": Decimal("1"),
        "rate_other": Decimal("2"),
        "single": 30000_00,
        "aggregate": 100000_00,
    },
    # 194J: professional/technical — 10% (2% technical/call-centre); threshold ₹30k.
    "194J": {
        "rate": Decimal("10"),
        "rate_technical": Decimal("2"),
        "single": 30000_00,
        "aggregate": 30000_00,
    },
    # 194H: commission/brokerage — 2% (w.e.f 01-Oct-2024); threshold ₹20k (FY25-26).
    "194H": {"rate": Decimal("2"), "single": 20000_00, "aggregate": 20000_00},
    # 194I: rent — 2% (plant & machinery) / 10% (land/building/furniture); threshold ₹2.4L.
    "194I": {
        "rate_plant": Decimal("2"),
        "rate_building": Decimal("10"),
        "single": 240000_00,
        "aggregate": 240000_00,
    },
}

MSME_PAYMENT_DAYS = 45  # MSMED Act s.15


def _round_rupee(paise: Decimal) -> int:
    return int((paise / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100


def tds_rate(section: str, *, payee_type: str = "company", category: str | None = None) -> Decimal:
    cfg = _TDS_SECTIONS[section]
    if section == "194C":
        return cfg["rate_individual"] if payee_type in ("individual", "huf") else cfg["rate_other"]
    if section == "194J":
        return cfg["rate_technical"] if category == "technical" else cfg["rate"]
    if section == "194I":
        return cfg["rate_plant"] if category == "plant" else cfg["rate_building"]
    return cfg["rate"]


def tds_on_payment(
    section: str,
    amount: int,
    *,
    payee_type: str = "company",
    category: str | None = None,
    aggregate_ytd: int = 0,
) -> dict[str, Any]:
    """TDS on a single payment of ``amount`` paise (taxable value). Applies when the single
    payment crosses the per-transaction threshold OR the running annual aggregate does."""
    cfg = _TDS_SECTIONS.get(section)
    if cfg is None:
        raise ValueError(f"unknown TDS section: {section}")
    amount = int(amount)
    applies = amount >= cfg["single"] or (aggregate_ytd + amount) >= cfg["aggregate"]
    if not applies:
        return {"applicable": False, "rate": Decimal("0"), "tds_paise": 0}
    rate = tds_rate(section, payee_type=payee_type, category=category)
    tds = _round_rupee(Decimal(amount) * rate / 100)
    return {"applicable": True, "rate": rate, "tds_paise": tds}


def three_way_match(
    po_amount: int, bill_amount: int, *, grn_amount: int | None = None, tolerance_pct: float = 5.0
) -> dict[str, Any]:
    """Match an invoice against its PO (and GRN if provided). ``matched`` is True only when
    every available variance is within ``tolerance_pct``."""
    tol = Decimal(str(tolerance_pct))

    def variance_pct(actual: int, expected: int) -> Decimal:
        if expected == 0:
            return Decimal("0") if actual == 0 else Decimal("100")
        return (abs(Decimal(actual) - Decimal(expected)) / Decimal(expected) * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    po_var = variance_pct(bill_amount, po_amount)
    grn_var = variance_pct(bill_amount, grn_amount) if grn_amount is not None else Decimal("0")
    matched = po_var <= tol and grn_var <= tol
    return {
        "matched": matched,
        "po_variance_pct": float(po_var),
        "grn_variance_pct": float(grn_var),
        "max_variance_pct": float(max(po_var, grn_var)),
    }


AGING_BUCKETS = ("0-30", "31-60", "61-90", "90+")


def aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 30:
        return "0-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def ap_aging(payables: list[dict], as_of: date) -> dict[str, Any]:
    """Bucket outstanding payables by age. Each item: {due_date, outstanding_paise}."""
    buckets = dict.fromkeys(AGING_BUCKETS, 0)
    total = 0
    for p in payables:
        outstanding = int(p["outstanding_paise"])
        if outstanding <= 0:
            continue
        days = (as_of - date.fromisoformat(p["due_date"])).days
        buckets[aging_bucket(days)] += outstanding
        total += outstanding
    return {"buckets": buckets, "total_outstanding": total}


def early_payment_discount(
    invoice_amount: int, *, discount_pct: float, discount_days: int, paid_in_days: int
) -> dict[str, Any]:
    """Capture an early-payment discount (e.g. "2/10 net 30": 2% off if paid within 10 days).
    The discount applies only when payment lands within the discount window."""
    eligible = paid_in_days <= discount_days
    discount = (
        _round_rupee(Decimal(invoice_amount) * Decimal(str(discount_pct)) / Decimal(100))
        if eligible
        else 0
    )
    return {
        "eligible": eligible,
        "discount": discount,
        "net_payable": int(invoice_amount) - discount,
    }
