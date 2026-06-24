"""GSTR-1 JSON export in the GSTN offline-utility schema — deferred feature (enhances gstr1)."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.gst.gst_calc import gstr1_json


def _b2b_line() -> dict:
    return {
        "invoice_no": "INV-9", "idt": "2026-05-10", "pos": "MH", "gstin": "27AAPFU0939F1ZV",
        "taxable": Paise.from_rupees(100000), "igst": 0,
        "cgst": Paise.from_rupees(9000), "sgst": Paise.from_rupees(9000),
        "hsn": "9983", "qty": 1, "val": Paise.from_rupees(118000),
    }


def _b2c_line() -> dict:
    return {
        "invoice_no": "INV-10", "idt": "2026-05-12", "pos": "KA", "gstin": None,
        "taxable": Paise.from_rupees(50000), "igst": Paise.from_rupees(9000),
        "cgst": 0, "sgst": 0, "hsn": "9983", "qty": 1,
    }


def test_period_and_top_level() -> None:
    out = gstr1_json([_b2b_line()], gstin="27AAPFU0939F1ZV", filing_period="2026-05")
    assert out["gstin"] == "27AAPFU0939F1ZV"
    assert out["fp"] == "052026"  # MMYYYY


def test_b2b_structure_rupees_and_date() -> None:
    out = gstr1_json([_b2b_line()], gstin="27AAA...", filing_period="2026-05")
    grp = out["b2b"][0]
    assert grp["ctin"] == "27AAPFU0939F1ZV"
    inv = grp["inv"][0]
    assert inv["inum"] == "INV-9"
    assert inv["idt"] == "10-05-2026"  # DD-MM-YYYY
    assert inv["pos"] == "27"  # MH -> numeric state code
    assert inv["val"] == 118000.0  # rupees, not paise
    det = inv["itms"][0]["itm_det"]
    assert det["txval"] == 100000.0 and det["rt"] == 18.0
    assert det["camt"] == 9000.0 and det["samt"] == 9000.0 and det["iamt"] == 0.0


def test_b2cs_and_hsn_aggregates() -> None:
    out = gstr1_json([_b2b_line(), _b2c_line()], gstin="27A", filing_period="2026-05")
    b2cs = out["b2cs"][0]
    assert b2cs["sply_ty"] == "INTER" and b2cs["pos"] == "29" and b2cs["txval"] == 50000.0
    # HSN 9983 aggregates both lines: 1,00,000 + 50,000 taxable
    hsn = out["hsn"]["data"][0]
    assert hsn["hsn_sc"] == "9983" and hsn["txval"] == 150000.0 and hsn["qty"] == 2
