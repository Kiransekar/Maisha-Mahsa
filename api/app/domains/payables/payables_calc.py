"""Payables computation core — pure, exact (integer paise), deterministic.

Covers the TDS-on-payments section engine (194C/194J/194H/194I) with rates + thresholds,
the PO↔GRN↔invoice 3-way match, AP aging, and the MSMED 45-day clock. TDS is computed on
the taxable value (excluding GST, per CBDT Circular 23/2017). Time is injected via ``as_of``.

Rates/thresholds are **FY 2025-26** and declared as data — re-verify each Finance Act
(see skills/indian-fin-rules).
"""

from __future__ import annotations

from datetime import date, timedelta
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
    # 194J: professional/technical — 10% (2% technical/call-centre). Threshold ₹50k from
    # FY 2025-26 (Finance Act 2025; MMX-1.0 §WS1.C1), was ₹30k.
    "194J": {
        "rate": Decimal("10"),
        "rate_technical": Decimal("2"),
        "single": 50000_00,
        "aggregate": 50000_00,
    },
    # 194H: commission/brokerage — 2% (w.e.f 01-Oct-2024); threshold ₹20k (FY25-26).
    "194H": {"rate": Decimal("2"), "single": 20000_00, "aggregate": 20000_00},
    # 194I: rent — 2% (plant & machinery) / 10% (land/building/furniture). From FY 2025-26 the
    # threshold is ₹50,000 PER MONTH (or part thereof); TDS applies to the full month's rent
    # once crossed, and there is NO annual-aggregate trigger (Finance Act 2025; §WS1.C2).
    "194I": {
        "rate_plant": Decimal("2"),
        "rate_building": Decimal("10"),
        "single": 50000_00,
        "per_month": True,  # per-payment threshold only; annual aggregate does not apply
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
    # STRICT ``>``, not ``>=``. Every one of these provisos exempts the payment when the amount
    # "does not exceed" the threshold — so AT exactly the threshold no deduction arises, and the
    # duty begins one paisa above it. Read verbatim from the Department's own text of the Acts and
    # confirmed by an adversarial re-fetch (2026-07-21):
    #   s.194J(1) first proviso cl.(B)(i) — "does not exceed ... fifty thousand rupees"
    #   s.194I proviso                    — "does not exceed fifty thousand rupees" (per month)
    #   s.194C(5)                         — "if such sum does not exceed thirty thousand rupees"
    # The engine previously used ``>=`` and deducted AT the threshold, i.e. tax the statute does not
    # require. Owner-approved correction 2026-07-21; mirrored in dif/src/recompute/tds.rs, which
    # carried the identical defect.
    if cfg.get("per_month"):
        # 194I: month-granular — TDS on the full month's rent once the per-month threshold is
        # exceeded; annual aggregate does not apply (§WS1.C2). ``amount`` is one month's rent.
        applies = amount > cfg["single"]
    else:
        applies = amount > cfg["single"] or (aggregate_ytd + amount) > cfg["aggregate"]
    if not applies:
        return {"applicable": False, "rate": Decimal("0"), "tds_paise": 0}
    rate = tds_rate(section, payee_type=payee_type, category=category)
    tds = _round_rupee(Decimal(amount) * rate / 100)
    return {"applicable": True, "rate": rate, "tds_paise": tds}


# ---- WS1.D1: 194Q / 194T / TCS s.394 / 206AA-206AB overlay -------------------------------
#
# NEW sections, kept separate from the ported ``tds_on_payment`` / ``_TDS_SECTIONS`` engine
# (194C/J/H/I) so the Py↔Rust recompute parity on that engine is untouched. Values that MMX-1.0
# §WS1.D1 states explicitly are inlined below; values it does NOT state are parameters with a
# ``None`` default that RAISES when the rule fires — never a silent wrong (or zero) deduction.
# See docs/SPEC-WS1D1.md.

# §WS1.D1: 194Q applies to purchases *exceeding* ₹50 lakh from a vendor in the FY. The same
# ₹50L crossing governs the TDS-primacy interplay with TCS 206C(1H)/s.394.
_PURCHASE_TDS_THRESHOLD = 5000000_00  # ₹50,00,000 (MMX-1.0 §WS1.D1)
_RATE_194Q = Decimal("0.1")  # 0.1% (MMX-1.0 §WS1.D1)
_RATE_194T = Decimal("10")  # 10% (MMX-1.0 §WS1.D1)
_THRESHOLD_194T = 20000_00  # ₹20,000 partner-payment threshold (MMX-1.0 §WS1.D1)


def _excess_over_threshold(amount: int, aggregate_ytd: int, threshold: int) -> int:
    """Incremental portion of this ``amount`` that lands *above* ``threshold`` given the FY
    running total ``aggregate_ytd`` already booked before it. Exact, in paise. Strictly-above
    semantics: at an aggregate of exactly ``threshold`` the excess is 0 (boundary excluded)."""
    prior_taxed = max(0, aggregate_ytd - threshold)
    new_taxed = max(0, aggregate_ytd + amount - threshold)
    return new_taxed - prior_taxed


def tds_194q(amount: int, *, aggregate_ytd: int = 0) -> dict[str, Any]:
    """194Q — buyer's TDS @0.1% on purchase value *exceeding* ₹50L per vendor per FY (MMX-1.0
    §WS1.D1). ``amount`` is this purchase (taxable value, ex-GST); ``aggregate_ytd`` is the FY
    running purchase total from this vendor booked before it. TDS falls only on the slice above
    ₹50L. When 194Q bites, TCS 206C(1H)/s.394 does NOT — TDS primacy — surfaced as
    ``tcs_206c_1h_suppressed``."""
    amount = int(amount)
    base = _excess_over_threshold(amount, int(aggregate_ytd), _PURCHASE_TDS_THRESHOLD)
    applies = base > 0
    tds = _round_rupee(Decimal(base) * _RATE_194Q / 100) if applies else 0
    return {
        "applicable": applies,
        "section": "194Q",
        "rate": _RATE_194Q,
        "taxable_paise": base,
        "tds_paise": tds,
        # TDS primacy: 194Q liability displaces the seller's 206C(1H)/s.394 collection.
        "tcs_206c_1h_suppressed": applies,
    }


def tds_194t(amount: int, *, aggregate_ytd: int = 0) -> dict[str, Any]:
    """194T — TDS @10% on partner remuneration/interest/commission *exceeding* ₹20,000 in the FY
    (MMX-1.0 §WS1.D1). Once the FY aggregate crosses ₹20,000 the tax is on the full payment
    ``amount``. Strictly-above: an aggregate of exactly ₹20,000 does not trigger."""
    amount = int(amount)
    applies = (int(aggregate_ytd) + amount) > _THRESHOLD_194T
    tds = _round_rupee(Decimal(amount) * _RATE_194T / 100) if applies else 0
    return {
        "applicable": applies,
        "section": "194T",
        "rate": _RATE_194T,
        "tds_paise": tds,
    }


def tcs_394_goods(
    amount: int, *, aggregate_ytd: int = 0, rate: Decimal | str | None = None,
    threshold: int | None = None,
) -> dict[str, Any]:
    """TCS on sale of goods — Income-tax Act 2025 s.394 (ex-206C(1H)). STRUCTURE ONLY: the rate
    and the receipt threshold are statutory and are NOT stated in MMX-1.0 §WS1.D1 → BLOCKED-CA.
    Both must be supplied from a CA-initialled oracle vector (§0.6); a fired rule with either
    missing RAISES rather than collect the wrong amount. Same 'excess over threshold' mechanic
    as 194Q."""
    if rate is None:
        raise ValueError("TCS s.394 rate is BLOCKED-CA (§0.6): supply the CA-sourced rate")
    if threshold is None:
        raise ValueError(
            "TCS s.394 threshold is BLOCKED-CA (§0.6): supply the CA-sourced threshold"
        )
    amount = int(amount)
    rate_d = Decimal(str(rate))
    base = _excess_over_threshold(amount, int(aggregate_ytd), int(threshold))
    applies = base > 0
    tcs = _round_rupee(Decimal(base) * rate_d / 100) if applies else 0
    return {
        "applicable": applies,
        "section": "394",
        "rate": rate_d,
        "taxable_paise": base,
        "tcs_paise": tcs,
    }


def apply_higher_rate(
    base_rate: Decimal | str,
    pan_available: bool,
    is_non_filer: bool,
    *,
    no_pan_rate: Decimal | str | None = None,
    non_filer_rate: Decimal | str | None = None,
) -> Decimal:
    """206AA / 206AB higher-rate overlay (MMX-1.0 §WS1.D1). Pure rate resolver a caller applies
    on top of any section's base rate — deliberately NOT baked into ``tds_on_payment``.

    Effective rate = the highest of ``base_rate`` and each triggered statutory floor:
      • no PAN → 206AA floor  • non-filer → 206AB floor (both can stack; the higher wins).

    The 206AA/206AB floor rates (e.g. the fixed percent, or 'twice the applicable rate') are
    statutory and are NOT stated in MMX-1.0 §WS1.D1 → BLOCKED-CA. When an overlay fires its
    floor must be supplied (CA-sourced, §0.6); a missing floor RAISES rather than silently
    under-deduct. With PAN present and a filer, no statutory number is needed and ``base_rate``
    passes through unchanged."""
    rate = Decimal(str(base_rate))
    if not pan_available:
        if no_pan_rate is None:
            raise ValueError(
                "206AA no-PAN floor is BLOCKED-CA (§0.6): supply CA-sourced no_pan_rate"
            )
        rate = max(rate, Decimal(str(no_pan_rate)))
    if is_non_filer:
        if non_filer_rate is None:
            raise ValueError(
                "206AB non-filer floor is BLOCKED-CA (§0.6): supply CA-sourced non_filer_rate"
            )
        rate = max(rate, Decimal(str(non_filer_rate)))
    return rate


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


# ---- MSME Form-1 half-yearly return (WS1.D8) --------------------------------------------
#
# Specified Companies (Furnishing of information about payment to micro and small enterprise
# suppliers) Order, 2019 under Companies Act 2013 s.405: amounts due to MSME-registered
# vendors outstanding beyond the MSMED Act s.15 45-day payment period (MSME_PAYMENT_DAYS
# above), reported in two half-yearly windows — MASTER_PLAN.md §WS1.D8:
#   April-September -> return due 31 October
#   October-March   -> return due 30 April


def msme_form1_period(for_date: date) -> dict[str, str]:
    """Resolve the MSME Form-1 half-yearly window containing ``for_date`` and its statutory
    return due date (MASTER_PLAN.md §WS1.D8). Pure; the date is injected, never read from a
    clock."""
    y = for_date.year
    if 4 <= for_date.month <= 9:
        start = date(y, 4, 1)
        end = date(y, 9, 30)
        due = date(y, 10, 31)
    elif for_date.month >= 10:
        start = date(y, 10, 1)
        end = date(y + 1, 3, 31)
        due = date(y + 1, 4, 30)
    else:  # Jan-Mar: second half of the FY that started the previous October
        start = date(y - 1, 10, 1)
        end = date(y, 3, 31)
        due = date(y, 4, 30)
    return {"start": start.isoformat(), "end": end.isoformat(), "due_date": due.isoformat()}


def msme_form1_pack(payables: list[dict], period_end: date) -> dict[str, Any]:
    """Build the MSME Form-1 half-yearly return data pack: amounts due to MSME-registered
    vendors outstanding beyond the MSMED Act s.15 45-day payment period (``MSME_PAYMENT_DAYS``),
    as of the half-year window containing ``period_end`` (MASTER_PLAN.md §WS1.D8). Pure —
    ``period_end`` is the injected reporting date, never the wall clock.

    Each item in ``payables``: {vendor_id, vendor_name, vendor_msme (bool), bill_date
    'YYYY-MM-DD', outstanding_paise}. ``reason_for_delay`` is a manual-entry placeholder per
    the Form-1 instructions — it is not derivable from ledger data.
    """
    period = msme_form1_period(period_end)
    lines: list[dict[str, Any]] = []
    total = 0
    for p in payables:
        if not p.get("vendor_msme"):
            continue
        outstanding = int(p["outstanding_paise"])
        if outstanding <= 0:
            continue
        bill_date = date.fromisoformat(p["bill_date"])
        days_outstanding = (period_end - bill_date).days
        if days_outstanding <= MSME_PAYMENT_DAYS:
            continue
        lines.append(
            {
                "vendor_id": p["vendor_id"],
                "vendor_name": p.get("vendor_name", ""),
                "bill_date": p["bill_date"],
                "outstanding_paise": outstanding,
                "days_outstanding": days_outstanding,
                "reason_for_delay": "",
            }
        )
        total += outstanding
    lines.sort(key=lambda ln: (-ln["days_outstanding"], ln["vendor_id"]))
    return {
        "period_start": period["start"],
        "period_end": period["end"],
        "return_due_date": period["due_date"],
        "total_outstanding_paise": total,
        "vendor_count": len(lines),
        "lines": lines,
    }


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


def _median(values: list[int]) -> int:
    s = sorted(values)
    return s[len(s) // 2]


def detect_recurring(
    bills: list[dict],
    *,
    min_occurrences: int = 3,
    gap_tolerance_days: int = 7,
    amount_tolerance_pct: float = 15.0,
) -> list[dict]:
    """Flag vendors with a regular (≈monthly) billing cadence as recurring payables (SaaS).
    Each bill: {vendor_id, vendor_name, bill_date 'YYYY-MM-DD', amount_paise}. A vendor is
    recurring when it has >= min_occurrences bills, a near-monthly median gap, and amounts
    within ``amount_tolerance_pct`` of the median. Predicts the next date + amount. Pure."""
    by_vendor: dict[Any, list[dict]] = {}
    for b in bills:
        by_vendor.setdefault(b["vendor_id"], []).append(b)

    out: list[dict] = []
    for vendor_id, items in by_vendor.items():
        if len(items) < min_occurrences:
            continue
        items = sorted(items, key=lambda x: x["bill_date"])
        dates = [date.fromisoformat(i["bill_date"]) for i in items]
        gaps = [(dates[k] - dates[k - 1]).days for k in range(1, len(dates))]
        median_gap = _median(gaps)
        if not (28 - gap_tolerance_days <= median_gap <= 31 + gap_tolerance_days):
            continue
        amounts = [int(i["amount_paise"]) for i in items]
        median_amount = _median(amounts)
        if median_amount <= 0:
            continue
        spread_pct = max(abs(a - median_amount) for a in amounts) / median_amount * 100
        if spread_pct > amount_tolerance_pct:
            continue
        out.append(
            {
                "vendor_id": vendor_id,
                "vendor_name": items[-1].get("vendor_name", ""),
                "occurrences": len(items),
                "median_gap_days": median_gap,
                "predicted_amount_paise": median_amount,
                "predicted_next_date": (dates[-1] + timedelta(days=median_gap)).isoformat(),
                "category": "saas_recurring",
            }
        )
    return out
