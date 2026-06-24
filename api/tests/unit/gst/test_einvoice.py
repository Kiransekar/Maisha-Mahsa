"""e-Invoice IRN + NIC-schema payload — deferred feature."""

from __future__ import annotations

import hashlib

from app.core.money import Paise
from app.domains.gst.gst_calc import compute_irn, einvoice_payload

_GSTIN = "27AAPFU0939F1ZV"


def test_irn_is_deterministic_64_hex_matching_spec() -> None:
    irn = compute_irn(_GSTIN, doc_no="INV-9", doc_date="2026-05-10")  # FY 2026-27
    assert len(irn) == 64 and irn == irn.lower()
    # independently reproduce the NIC hash: GSTIN + FY + DocType + DocNo
    expected = hashlib.sha256(f"{_GSTIN}2026-27INVINV-9".encode()).hexdigest()
    assert irn == expected
    # same inputs -> same IRN; different doc -> different IRN
    assert compute_irn(_GSTIN, doc_no="INV-9", doc_date="2026-05-10") == irn
    assert compute_irn(_GSTIN, doc_no="INV-10", doc_date="2026-05-10") != irn


def test_financial_year_boundary() -> None:
    # March is the previous FY; April starts the new one
    assert compute_irn(_GSTIN, doc_no="X", doc_date="2026-03-31") != compute_irn(
        _GSTIN, doc_no="X", doc_date="2026-04-01"
    )


def test_payload_schema_and_qr() -> None:
    p = einvoice_payload(
        seller_gstin=_GSTIN, buyer_gstin="29AAB...", doc_no="INV-9", doc_date="2026-05-10",
        taxable=Paise.from_rupees(100000), igst=0,
        cgst=Paise.from_rupees(9000), sgst=Paise.from_rupees(9000),
        total=Paise.from_rupees(118000), hsn="9983",
    )
    assert p["Version"] == "1.1"
    assert p["DocDtls"] == {"Typ": "INV", "No": "INV-9", "Dt": "10/05/2026"}
    assert p["SellerDtls"]["Gstin"] == _GSTIN
    assert p["TranDtls"]["SupTyp"] == "B2B"
    assert p["ValDtls"]["TotInvVal"] == 118000.0  # rupees
    assert p["ItemList"][0]["GstRt"] == 18.0
    # IRN is present and matches the standalone computation; QR carries it
    assert p["Irn"] == compute_irn(_GSTIN, doc_no="INV-9", doc_date="2026-05-10")
    assert p["QrData"]["Irn"] == p["Irn"] and p["QrData"]["MainHsnCode"] == "9983"


def test_b2c_when_no_buyer_gstin() -> None:
    p = einvoice_payload(
        seller_gstin=_GSTIN, buyer_gstin=None, doc_no="INV-11", doc_date="2026-05-10",
        taxable=Paise.from_rupees(5000), igst=Paise.from_rupees(900), cgst=0, sgst=0,
        total=Paise.from_rupees(5900),
    )
    assert p["TranDtls"]["SupTyp"] == "B2C"
    assert p["BuyerDtls"]["Gstin"] == "URP"
