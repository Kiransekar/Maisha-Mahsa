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
def test_itc_setoff_igst_credit_cash_minimizing():
    # Rule 88A ("in any order and in any proportion"): IGST credit ₹150 covers the uncovered
    # needs first — ₹80 CGST (₹100 − ₹20 own credit), then ₹70 of the ₹80 SGST need; own
    # credits fill the rest, leaving ₹10 SGST cash. The old fixed IGST→CGST-first order
    # stranded the ₹20 CGST credit and paid ₹30 cash.
    out = {"igst": 0, "cgst": Paise.from_rupees(100), "sgst": Paise.from_rupees(100)}
    cr = {
        "igst": Paise.from_rupees(150),
        "cgst": Paise.from_rupees(20),
        "sgst": Paise.from_rupees(20),
    }
    res = g.itc_setoff(out, cr)
    assert res["cash"] == {"igst": 0, "cgst": 0, "sgst": Paise.from_rupees(10)}
    assert res["remaining_credit"] == {"igst": 0, "cgst": 0, "sgst": 0}


def test_itc_setoff_allocation_boundary_paired():
    # PAIRED boundary: IGST credit exactly covers both uncovered needs (8000 + 7000) -> nil
    # cash; one paisa short -> exactly one paisa of cash on SGST (the tie-break tail).
    out = {"igst": 0, "cgst": 10000, "sgst": 10000}
    at = g.itc_setoff(out, {"igst": 15000, "cgst": 2000, "sgst": 3000})
    assert at["cash"] == {"igst": 0, "cgst": 0, "sgst": 0}
    assert at["remaining_credit"] == {"igst": 0, "cgst": 0, "sgst": 0}
    past = g.itc_setoff(out, {"igst": 14999, "cgst": 2000, "sgst": 3000})
    assert past["cash"] == {"igst": 0, "cgst": 0, "sgst": 1}
    assert past["remaining_credit"] == {"igst": 0, "cgst": 0, "sgst": 0}


def test_itc_setoff_mandatory_exhaustion_displaces_own_credit():
    # Rule 88A proviso: IGST credit is "completely exhausted mandatorily" even where own credit
    # could cover the head — displaced CGST credit carries forward, cash stays nil.
    res = g.itc_setoff(
        {"igst": 0, "cgst": 5000, "sgst": 5000}, {"igst": 12000, "cgst": 4000, "sgst": 0}
    )
    assert res["cash"] == {"igst": 0, "cgst": 0, "sgst": 0}
    assert res["remaining_credit"] == {"igst": 2000, "cgst": 4000, "sgst": 0}


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


def test_late_fee_aato_caps_notf_19_2021():
    # D4 fix pinned: Notf 19/2021 turnover-linked caps (combined CGST+SGST paise).
    cr_1_5 = 1_500_000_000  # ₹1.5 crore, paise
    cr_5 = 5_000_000_000  # ₹5 crore, paise
    # AATO ≤ ₹1.5cr: ₹2,000 combined cap, binding from day 40.
    assert g.late_fee_3b(39, aato=cr_1_5) == Paise.from_rupees(1950)
    assert g.late_fee_3b(40, aato=cr_1_5) == Paise.from_rupees(2000)
    assert g.late_fee_3b(41, aato=cr_1_5) == Paise.from_rupees(2000)
    # One paisa above ₹1.5cr -> ₹5,000 combined cap, binding from day 100.
    assert g.late_fee_3b(99, aato=cr_1_5 + 1) == Paise.from_rupees(4950)
    assert g.late_fee_3b(100, aato=cr_1_5 + 1) == Paise.from_rupees(5000)
    assert g.late_fee_3b(201, aato=cr_5) == Paise.from_rupees(5000)
    # Above ₹5cr, and unknown AATO, fall back to the s.47(1) statutory maximum — never a
    # silent undercharge.
    assert g.late_fee_3b(201, aato=cr_5 + 1) == Paise.from_rupees(10000)
    assert g.late_fee_3b(201) == Paise.from_rupees(10000)
    # The nil-return cap is turnover-independent (Sl.1 carve-out in Sl.2/Sl.3).
    assert g.late_fee_3b(26, is_nil=True, aato=cr_1_5) == Paise.from_rupees(500)


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


def test_gstr3b_route_threads_aato_to_service(session):
    """FINAL-AUDIT pin: POST /api/gst/gstr3b must pass ``body.aato`` through to the service.
    The route silently dropped it after the D4 fix (schema + service took aato, the route
    call didn't), so a small taxpayer's supplied turnover was ignored and the s.47(1)
    ₹10,000 max cap was persisted instead of the Notf 19/2021 ₹2,000 cap."""
    from app.domains.gst.router import file_gstr3b as route
    from app.domains.gst.schemas import Gstr3bInput

    body = Gstr3bInput(
        filing_period="2026-05",
        due_date="2026-01-01",
        filed_date="2026-07-20",  # 200 days late — deep past every cap
        aato=1_500_000_000,  # ₹1.5 crore -> ₹2,000 combined cap
        output={"igst": 0, "cgst": 0, "sgst": 0},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
    )
    result = route(body, db=session)
    assert result.late_fee == Paise.from_rupees(2000)  # not the ₹10,000 unknown-AATO max
