"""GST computation core — pure, exact (integer paise), deterministic.

Covers GSTIN validation (format + check digit), the statutory ITC set-off order
(CGST Act s.49/49A/49B read with Rule 88A), GSTR-3B cash liability, late fee + interest,
and the GSTR-1 outward-supply summary. No clock is read; ``days_late`` is passed in.

Re-verify rates/caps against the current Finance Act (see skills/indian-fin-rules).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
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
    """Apply input-tax credit against output tax (CGST Act s.49(5)/49A/49B r/w Rule 88A).

    Order applied:
      1. IGST credit → IGST liability (Rule 88A: "shall first be utilised").
      2. Remaining IGST credit → CGST/SGST liability. Rule 88A r/w Circular No. 98/17/2019-GST
         permits this "in any order and in any proportion", and the IGST credit must be
         "completely exhausted mandatorily" before any CGST/SGST credit is used. We choose the
         CASH-MINIMIZING split: first cover each head's uncovered need (liability minus its own
         credit) — CGST before SGST when the credit cannot cover both (total cash is invariant
         to that tie-break, only the per-head split moves) — then exhaust any leftover IGST
         credit against remaining liability, CGST first (displaced own credit carries forward).
         Interpretation choice recorded in ws1d_itc_setoff.yaml (ca_initials: OWNER).
      3. CGST credit → CGST then IGST; SGST credit → SGST then IGST. CGST and SGST credit
         never cross (s.49(5)(c)/(d) provisos).

    Deterministic, clock-free, integer paise. Returns the remaining cash payable per head and
    the unutilised credit."""
    out = _heads(output)
    cr = _heads(credit)

    def apply(src: str, dst: str, cap: int | None = None) -> None:
        amt = min(cr[src], out[dst])
        if cap is not None:
            amt = min(amt, cap)
        cr[src] -= amt
        out[dst] -= amt

    apply("igst", "igst")
    # Rule 88A cash-minimizing allocation: uncovered needs first, then mandatory exhaustion.
    apply("igst", "cgst", cap=max(0, out["cgst"] - cr["cgst"]))
    apply("igst", "sgst", cap=max(0, out["sgst"] - cr["sgst"]))
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


def _round_rupee(paise: Decimal | int) -> int:
    # Accepts an EXACT Decimal — callers must not pre-truncate with int() (§WS1.C3).
    rupees = (Decimal(paise) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rupees) * 100


def hsn_rate(code: str, master: dict[str, float]) -> dict[str, Any]:
    """Look up the GST rate for an HSN/SAC code in a rate master. A valid code is 4/6/8 digits
    (HSN) or 6 digits (SAC); ``found`` is False when the code isn't in the master."""
    digits = code.strip()
    well_formed = digits.isdigit() and len(digits) in (4, 6, 8)
    rate = master.get(digits)
    return {"hsn": digits, "rate": rate, "found": rate is not None, "well_formed": well_formed}


def rcm_liability(supplies: list[dict]) -> dict[str, Any]:
    """Reverse-charge mechanism: on notified inward supplies (e.g. legal, GTA, imports) the
    recipient pays the GST and self-invoices. The same amount is available as ITC when eligible.
    Each supply: {taxable, rate} (taxable in paise, rate as a percent)."""
    total_taxable = 0
    total_tax = 0
    for s in supplies:
        taxable = int(s["taxable"])
        tax = _round_rupee(Decimal(taxable) * Decimal(str(s["rate"])) / 100)
        total_taxable += taxable
        total_tax += tax
    return {
        "taxable_value": total_taxable,
        "rcm_tax_payable": total_tax,
        "itc_available": total_tax,  # full ITC when the inward supply is eligible
    }


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


# ---- Composition scheme + LUT (exports) -----------------------------------------------

# Composition levy rates (CGST+SGST combined) by business category.
_COMPOSITION_RATES = {
    "trader": Decimal("0.01"),
    "manufacturer": Decimal("0.01"),
    "restaurant": Decimal("0.05"),
    "service": Decimal("0.06"),
}


def composition_tax(turnover: int, *, category: str) -> dict[str, Any]:
    """Composition-scheme tax = turnover × the category levy rate (s.10). 1% trader/manufacturer,
    5% restaurant, 6% other services."""
    rate = _COMPOSITION_RATES.get(category)
    if rate is None:
        raise ValueError(f"unknown composition category: {category}")
    return {
        "category": category,
        "rate_pct": float(rate * 100),
        "turnover": int(turnover),
        "tax": _round_rupee(Decimal(int(turnover)) * rate),
    }


def lut_export(taxable: int) -> dict[str, Any]:
    """Export under a Letter of Undertaking is zero-rated — no IGST is charged and input ITC is
    refundable (CGST Act s.16, IGST Act s.16)."""
    return {
        "taxable": int(taxable),
        "igst": 0,
        "zero_rated": True,
        "note": "Export under LUT — zero-rated, no IGST charged; claim ITC refund.",
    }


def lut_validity(issue_date: str) -> str:
    """A LUT is valid for the financial year of issue → expires 31 March of that FY."""
    d = date.fromisoformat(issue_date)
    end_year = d.year + 1 if d.month >= 4 else d.year
    return f"{end_year}-03-31"


# ---- e-Invoice IRN + NIC schema -------------------------------------------------------

# WS9.3: the IRN below is computed locally (same NIC hash algorithm) but never registered with
# the IRP — it has no legal force as an e-invoice until the real IRP call happens (out of scope
# here). Every surface that shows this IRN (JSON payload, PDF, QR caption) MUST carry this exact
# label so a human never mistakes a draft number for a filed one. See scripts/check_no_draft_irn.sh.
DRAFT_IRN_LABEL = "DRAFT — not IRP-registered; not a valid e-invoice until registered"


def _einvoice_fy(iso_date: str) -> str:
    """Financial year (YYYY-YY) for a document date (Apr–Mar)."""
    y, m, _ = (int(x) for x in iso_date.split("-"))
    start = y if m >= 4 else y - 1
    return f"{start}-{str(start + 1)[2:]}"


def compute_irn(seller_gstin: str, *, doc_no: str, doc_date: str, doc_type: str = "INV") -> str:
    """The 64-char IRN = SHA-256 of SupplierGSTIN + FY + DocType + DocNo (NIC algorithm).
    Deterministic and independently verifiable — the same as the IRP computes."""
    fy = _einvoice_fy(doc_date)
    payload = f"{seller_gstin.upper()}{fy}{doc_type.upper()}{doc_no}"
    return hashlib.sha256(payload.encode()).hexdigest()


def einvoice_payload(
    *,
    seller_gstin: str,
    buyer_gstin: str | None,
    doc_no: str,
    doc_date: str,
    taxable: int,
    igst: int,
    cgst: int,
    sgst: int,
    total: int,
    hsn: str | None = None,
    item_count: int = 1,
    doc_type: str = "INV",
) -> dict[str, Any]:
    """Build the e-invoice in the NIC schema (Version 1.1) plus the computed IRN and the QR data
    block. The IRP signs the QR at registration — that external call is out of scope here; this
    is the deterministic, locally-verifiable part (IRN + canonical payload)."""
    irn = compute_irn(seller_gstin, doc_no=doc_no, doc_date=doc_date, doc_type=doc_type)
    dt = _to_ddmmyyyy(doc_date).replace("-", "/")  # NIC wants DD/MM/YYYY
    sup_typ = "B2B" if buyer_gstin else "B2C"
    payload = {
        "Version": "1.1",
        "Irn": irn,
        "IrnStatus": DRAFT_IRN_LABEL,
        "TranDtls": {"TaxSch": "GST", "SupTyp": sup_typ, "RegRev": "N"},
        "DocDtls": {"Typ": doc_type, "No": doc_no, "Dt": dt},
        "SellerDtls": {"Gstin": seller_gstin.upper()},
        "BuyerDtls": {"Gstin": (buyer_gstin or "URP").upper()},
        "ItemList": [
            {
                "SlNo": "1",
                "HsnCd": hsn or "",
                "Qty": item_count,
                "AssAmt": _to_rupees(taxable),
                "GstRt": _gst_rate(taxable, igst, cgst, sgst),
                "IgstAmt": _to_rupees(igst),
                "CgstAmt": _to_rupees(cgst),
                "SgstAmt": _to_rupees(sgst),
                "TotItemVal": _to_rupees(total),
            }
        ],
        "ValDtls": {
            "AssVal": _to_rupees(taxable),
            "IgstVal": _to_rupees(igst),
            "CgstVal": _to_rupees(cgst),
            "SgstVal": _to_rupees(sgst),
            "TotInvVal": _to_rupees(total),
        },
        # The data the signed QR encodes (the IRP returns a JWT-signed version of this).
        "QrData": {
            "SellerGstin": seller_gstin.upper(),
            "BuyerGstin": buyer_gstin or "URP",
            "DocNo": doc_no,
            "DocTyp": doc_type,
            "DocDt": dt,
            "TotInvVal": _to_rupees(total),
            "ItemCnt": item_count,
            "MainHsnCode": hsn or "",
            "Irn": irn,
            # rendered under/beside the QR image wherever this data is shown as a caption
            "Caption": DRAFT_IRN_LABEL,
        },
    }
    return payload


# ---- GSTR-1 JSON export (GSTN offline-utility schema) ---------------------------------

# 2-letter → numeric GST state codes (place of supply). Unknown codes pass through.
_STATE_CODES = {
    "JK": "01",
    "HP": "02",
    "PB": "03",
    "CH": "04",
    "UK": "05",
    "HR": "06",
    "DL": "07",
    "RJ": "08",
    "UP": "09",
    "BR": "10",
    "SK": "11",
    "AR": "12",
    "NL": "13",
    "MN": "14",
    "MZ": "15",
    "TR": "16",
    "ML": "17",
    "AS": "18",
    "WB": "19",
    "JH": "20",
    "OR": "21",
    "CG": "22",
    "MP": "23",
    "GJ": "24",
    "MH": "27",
    "KA": "29",
    "GA": "30",
    "KL": "32",
    "TN": "33",
    "PY": "34",
    "AN": "35",
    "TG": "36",
    "AP": "37",
    "LD": "31",
    "LA": "38",
}


def _to_rupees(paise: Any) -> float:
    return round(int(paise) / 100, 2)


def _gst_rate(taxable: int, igst: int, cgst: int, sgst: int) -> float:
    tax = igst if igst else (cgst + sgst)
    return round(tax / taxable * 100, 2) if taxable else 0.0


def _to_ddmmyyyy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def gstr1_json(
    lines: list[dict], *, gstin: str, filing_period: str, gross_turnover: int | None = None
) -> dict[str, Any]:
    """Build the GSTR-1 return in the GSTN offline-utility JSON schema from outward-supply
    lines (as produced by ``RevenueService.gstr1_lines``). Amounts are rupee decimals, dates
    ``DD-MM-YYYY``, period ``MMYYYY``; lines with a buyer GSTIN go to B2B, the rest to B2CS."""
    fp = filing_period[5:7] + filing_period[:4]  # "YYYY-MM" -> "MMYYYY"
    b2b: dict[str, dict[str, dict]] = {}  # ctin -> {inum -> invoice}
    b2cs: dict[tuple, dict[str, int]] = {}  # (pos, rt, sply_ty) -> sums
    hsn: dict[str, dict[str, Any]] = {}

    for ln in lines:
        taxable = int(ln.get("taxable", 0))
        igst, cgst, sgst = int(ln.get("igst", 0)), int(ln.get("cgst", 0)), int(ln.get("sgst", 0))
        rt = _gst_rate(taxable, igst, cgst, sgst)
        pos = _STATE_CODES.get((ln.get("pos") or "").upper(), ln.get("pos") or "")
        item = {
            "num": 1,
            "itm_det": {
                "txval": _to_rupees(taxable),
                "rt": rt,
                "iamt": _to_rupees(igst),
                "camt": _to_rupees(cgst),
                "samt": _to_rupees(sgst),
                "csamt": 0,
            },
        }
        buyer = ln.get("gstin")
        if buyer:
            inv = {
                "inum": ln.get("invoice_no"),
                "idt": _to_ddmmyyyy(ln["idt"]) if ln.get("idt") else "",
                "val": _to_rupees(ln.get("val", taxable + igst + cgst + sgst)),
                "pos": pos,
                "rchrg": "N",
                "inv_typ": "R",
                "itms": [item],
            }
            b2b.setdefault(buyer, {})[str(inv["inum"])] = inv
        else:
            key = (pos, rt, "INTER" if igst else "INTRA")
            agg = b2cs.setdefault(key, {"txval": 0, "iamt": 0, "camt": 0, "samt": 0})
            agg["txval"] += taxable
            agg["iamt"] += igst
            agg["camt"] += cgst
            agg["samt"] += sgst
        code = ln.get("hsn")
        if code:
            h = hsn.setdefault(
                code, {"txval": 0, "iamt": 0, "camt": 0, "samt": 0, "qty": 0, "rt": rt}
            )
            h["txval"] += taxable
            h["iamt"] += igst
            h["camt"] += cgst
            h["samt"] += sgst
            h["qty"] += int(ln.get("qty", 0))

    out: dict[str, Any] = {"gstin": gstin, "fp": fp}
    if gross_turnover is not None:
        out["gt"] = _to_rupees(gross_turnover)
    if b2b:
        out["b2b"] = [{"ctin": ctin, "inv": list(invs.values())} for ctin, invs in b2b.items()]
    if b2cs:
        out["b2cs"] = [
            {
                "sply_ty": sply,
                "pos": pos,
                "typ": "OE",
                "rt": rt,
                "txval": _to_rupees(v["txval"]),
                "iamt": _to_rupees(v["iamt"]),
                "camt": _to_rupees(v["camt"]),
                "samt": _to_rupees(v["samt"]),
                "csamt": 0,
            }
            for (pos, rt, sply), v in b2cs.items()
        ]
    if hsn:
        out["hsn"] = {
            "data": [
                {
                    "num": i + 1,
                    "hsn_sc": code,
                    "uqc": "NA",
                    "qty": v["qty"],
                    "rt": v["rt"],
                    "txval": _to_rupees(v["txval"]),
                    "iamt": _to_rupees(v["iamt"]),
                    "camt": _to_rupees(v["camt"]),
                    "samt": _to_rupees(v["samt"]),
                    "csamt": 0,
                }
                for i, (code, v) in enumerate(hsn.items())
            ]
        }
    return out


# ---- GSTR-9 annual return -------------------------------------------------------------


def gstr9_annual(gstr1_totals: list[dict], gstr3b_periods: list[dict]) -> dict[str, Any]:
    """Consolidate a year into the GSTR-9 annual return from monthly artefacts:
    ``gstr1_totals`` are the per-period ``build_gstr1(...)['totals']`` (outward supplies);
    ``gstr3b_periods`` are per-period ``{output:{igst,cgst,sgst}, itc:{igst,cgst,sgst},
    tax_paid_cash}``. Surfaces the GSTR-1-vs-3B differential (the reconciliation GSTR-9 exists
    to expose): differential > 0 means tax under-declared in GSTR-3B (additional liability)."""
    outward = {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0}
    for t in gstr1_totals:
        for key in outward:
            outward[key] += int(t.get(key, 0))
    outward["total_tax"] = outward["igst"] + outward["cgst"] + outward["sgst"]

    output3b = {"igst": 0, "cgst": 0, "sgst": 0}
    itc = {"igst": 0, "cgst": 0, "sgst": 0}
    cash = 0
    for p in gstr3b_periods:
        for head in output3b:
            output3b[head] += int(p.get("output", {}).get(head, 0))
            itc[head] += int(p.get("itc", {}).get(head, 0))
        cash += int(p.get("tax_paid_cash", 0))
    output3b_total = sum(output3b.values())
    differential = outward["total_tax"] - output3b_total

    return {
        "periods": len(gstr3b_periods),
        "outward_per_gstr1": outward,
        "output_tax_per_gstr3b": {**output3b, "total": output3b_total},
        "itc_availed": {**itc, "total": sum(itc.values())},
        "tax_paid_cash": cash,
        "differential_tax": differential,  # >0: under-declared in 3B; <0: excess
        "reconciled": differential == 0,
    }
