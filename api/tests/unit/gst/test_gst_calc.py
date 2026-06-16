"""GST computation checks — GSTIN validation, ITC set-off, GSTR-3B, GSTR-1 summary.
Money is paise; expected values are worked out in comments."""

from app.core.money import Paise
from app.domains.gst import gst_calc as g

# A structurally-valid GSTIN with a self-consistent check digit (computed, not guessed).
_FIRST14 = "27AAPFU0939F1Z"
VALID_GSTIN = _FIRST14 + g.gstin_check_digit(_FIRST14)


# ---- GSTIN ----
def test_gstin_valid_and_checkdigit_roundtrip():
    assert g.validate_gstin(VALID_GSTIN) is True
    # the widely-published sample 27AAPFU0939F1ZV must validate with the same algorithm
    assert g.validate_gstin("27AAPFU0939F1ZV") is True


def test_gstin_rejects_bad_checkdigit_and_structure():
    wrong = VALID_GSTIN[:14] + ("A" if VALID_GSTIN[14] != "A" else "B")
    assert g.validate_gstin(wrong) is False
    assert g.validate_gstin("27AAPFU0939F1Z") is False  # 14 chars
    assert g.validate_gstin("99AAPFU0939F1ZV") is False  # bad state code
    assert g.validate_gstin("") is False
    assert g.validate_gstin(None) is False


# ---- ITC set-off ----
def test_itc_setoff_igst_credit_cascades():
    # IGST credit ₹150 covers ₹100 CGST then ₹50 SGST; SGST credit clears remaining ₹50 SGST.
    out = {"igst": 0, "cgst": Paise.from_rupees(100), "sgst": Paise.from_rupees(100)}
    cr = {
        "igst": Paise.from_rupees(150),
        "cgst": Paise.from_rupees(20),
        "sgst": Paise.from_rupees(20),
    }
    res = g.itc_setoff(out, cr)
    assert res["cash"] == {"igst": 0, "cgst": 0, "sgst": Paise.from_rupees(30)}
    assert res["remaining_credit"]["cgst"] == Paise.from_rupees(20)


def test_itc_cgst_cannot_offset_sgst():
    # CGST credit may not touch SGST output -> SGST must be paid in cash.
    out = {"igst": 0, "cgst": 0, "sgst": Paise.from_rupees(100)}
    cr = {"igst": 0, "cgst": Paise.from_rupees(100), "sgst": 0}
    res = g.itc_setoff(out, cr)
    assert res["cash"]["sgst"] == Paise.from_rupees(100)
    assert res["remaining_credit"]["cgst"] == Paise.from_rupees(100)


# ---- GSTR-3B late fee / interest ----
def test_late_fee_normal_nil_and_cap():
    assert g.late_fee_3b(5) == Paise.from_rupees(250)  # ₹50/day × 5
    assert g.late_fee_3b(5, is_nil=True) == Paise.from_rupees(100)  # ₹20/day × 5
    assert g.late_fee_3b(1000) == Paise.from_rupees(10000)  # capped
    assert g.late_fee_3b(0) == 0


def test_interest_18pct_simple():
    # ₹10,000 × 18% × 30/365 = ₹147.95 -> ₹148
    assert g.interest_3b(Paise.from_rupees(10000), 30) == Paise.from_rupees(148)
    assert g.interest_3b(Paise.from_rupees(10000), 0) == 0


def test_compute_gstr3b_end_to_end():
    out = {"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)}
    res = g.compute_gstr3b(out, {"igst": 0, "cgst": 0, "sgst": 0}, days_late=5)
    assert res["cash_total"] == Paise.from_rupees(10000)
    assert res["late_fee"] == Paise.from_rupees(250)
    assert res["total_payable"] == res["cash_total"] + res["late_fee"] + res["interest"]


# ---- GSTR-1 summary ----
def test_build_gstr1_groups_and_validates():
    lines = [
        {
            "invoice_no": "INV1",
            "taxable": Paise.from_rupees(1000),
            "igst": Paise.from_rupees(180),
            "hsn": "9983",
            "gstin": VALID_GSTIN,
        },
        {
            "invoice_no": "INV2",
            "taxable": Paise.from_rupees(500),
            "cgst": Paise.from_rupees(45),
            "sgst": Paise.from_rupees(45),
            "hsn": "9983",
        },
        {"invoice_no": "INV3", "taxable": Paise.from_rupees(200), "igst": Paise.from_rupees(36)},
    ]
    summary = g.build_gstr1(lines, filing_period="2026-05")
    assert VALID_GSTIN in summary["b2b"]
    assert summary["b2c"]["taxable"] == Paise.from_rupees(700)  # INV2 + INV3
    assert summary["hsn"]["9983"]["taxable"] == Paise.from_rupees(1500)
    assert summary["totals"]["total_tax"] == Paise.from_rupees(306)
    assert any("missing HSN" in e for e in summary["errors"])  # INV3 has no HSN


def test_build_gstr1_flags_invalid_gstin():
    lines = [{"invoice_no": "X", "taxable": 100, "hsn": "9983", "gstin": "27AAPFU0939F1ZA"}]
    summary = g.build_gstr1(lines, filing_period="2026-05")
    assert any("invalid GSTIN" in e for e in summary["errors"])
