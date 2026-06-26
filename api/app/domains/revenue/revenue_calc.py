"""Revenue computation core — pure, exact (integer paise), deterministic.

Covers GST-compliant invoice computation (intra-state CGST+SGST vs inter-state IGST), TDS
on the taxable value, AR-aging buckets, the dunning reminder schedule, and credit-note
timeliness (CGST Act s.34). Time is injected via ``as_of`` — no clock is read.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _round_paise(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_invoice(
    items: list[dict],
    *,
    gst_rate: float | Decimal,
    inter_state: bool,
    tds_rate: float | Decimal = 0,
) -> dict[str, int]:
    """Compute an invoice's tax split, total, TDS and net receivable. ``items`` are
    {quantity:int, rate:int_paise}. Intra-state splits GST into equal CGST+SGST; inter-state
    is a single IGST line. TDS is computed on the taxable value (not on GST)."""
    rate = Decimal(str(gst_rate))
    subtotal = sum(int(it["quantity"]) * int(it["rate"]) for it in items)

    igst = cgst = sgst = 0
    if inter_state:
        igst = _round_paise(Decimal(subtotal) * rate / 100)
    else:
        cgst = _round_paise(Decimal(subtotal) * rate / 200)
        sgst = cgst
    total_tax = igst + cgst + sgst
    total_amount = subtotal + total_tax

    tds_amount = _round_paise(Decimal(subtotal) * Decimal(str(tds_rate)) / 100)
    net_receivable = total_amount - tds_amount

    return {
        "subtotal": subtotal,
        "igst_amount": igst,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "total_tax": total_tax,
        "total_amount": total_amount,
        "tds_amount": tds_amount,
        "net_receivable": net_receivable,
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


def ar_aging(receivables: list[dict], as_of: date) -> dict[str, Any]:
    """Bucket outstanding receivables by age. Each item: {due_date, outstanding_paise}."""
    buckets = dict.fromkeys(AGING_BUCKETS, 0)
    total = 0
    for r in receivables:
        outstanding = int(r["outstanding_paise"])
        if outstanding <= 0:
            continue
        days = (as_of - date.fromisoformat(r["due_date"])).days
        buckets[aging_bucket(days)] += outstanding
        total += outstanding
    return {"buckets": buckets, "total_outstanding": total}


_DUNNING_SCHEDULE = {-7: "T-7", -3: "T-3", -1: "T-1", 1: "T+1", 7: "T+7"}


def dunning_due(due_date: str, as_of: date) -> list[str]:
    """Reminder labels that fall exactly on ``as_of`` for an invoice with this due date."""
    due = date.fromisoformat(due_date)
    return [label for offset, label in _DUNNING_SCHEDULE.items() if (due - as_of).days == -offset]


def credit_note_deadline(invoice_date: str) -> date:
    """CGST s.34: a credit note's GST may be adjusted only up to 30 November following the
    end of the financial year (Apr–Mar) of the original supply."""
    d = date.fromisoformat(invoice_date)
    fy_following_year = d.year + 1 if d.month >= 4 else d.year
    return date(fy_following_year, 11, 30)


def is_credit_note_timely(invoice_date: str, cn_date: str) -> bool:
    return date.fromisoformat(cn_date) <= credit_note_deadline(invoice_date)


def export_invoice(
    taxable: int, *, with_lut: bool, igst_rate: float = 18.0, invoice_date: str
) -> dict[str, Any]:
    """Export invoice — a zero-rated supply (IGST Act s.16). With a LUT/bond, no IGST is
    charged; without one, IGST is charged and refundable. FEMA requires export proceeds to be
    realised within 9 months of the invoice date. Money in paise. Pure."""
    import calendar

    rate = Decimal("0") if with_lut else Decimal(str(igst_rate)) / Decimal(100)
    igst = _round_paise(Decimal(int(taxable)) * rate)
    inv = date.fromisoformat(invoice_date)
    months = inv.month - 1 + 9
    year = inv.year + months // 12
    month = months % 12 + 1
    day = min(inv.day, calendar.monthrange(year, month)[1])
    return {
        "zero_rated": True,
        "with_lut": with_lut,
        "igst": igst,
        "total": int(taxable) + igst,
        "refund_eligible": (not with_lut) and igst > 0,
        "realization_due_date": date(year, month, day).isoformat(),
    }


def deferred_revenue_schedule(total: int, *, start: str, months: int, as_of: str) -> dict[str, Any]:
    """Straight-line revenue recognition for a contract: recognise ``total`` ratably over
    ``months`` from ``start``. Returns recognised-to-date vs deferred at ``as_of`` (the final
    period absorbs rounding so recognised never exceeds the total)."""
    if months <= 0:
        raise ValueError("months must be positive")
    s = date.fromisoformat(start)
    a = date.fromisoformat(as_of)
    elapsed = (a.year - s.year) * 12 + (a.month - s.month)
    elapsed = max(0, min(months, elapsed))
    monthly = _round_paise(Decimal(int(total)) / months)
    recognized = int(total) if elapsed >= months else min(int(total), monthly * elapsed)
    return {
        "total": int(total),
        "monthly": monthly,
        "months_elapsed": elapsed,
        "recognized": recognized,
        "deferred": int(total) - recognized,
    }
