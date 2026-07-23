"""WS1.D7 — e-way bill threshold engine + JSON artifact.

Spec-cited value: ₹50,000 inter-state consignment-value trigger (WS1.D7). Intra-state thresholds
are per-state (WS2 packs) and injected here, never hard-coded.
"""

from app.core.money import Paise
from app.domains.gst import eway


# ---- inter-state ₹50,000 boundary ----
def test_inter_state_at_and_below_threshold():
    base = {"from_state": "MH", "to_state": "GJ"}

    at = eway.eway_required({**base, "value": Paise.from_rupees(50_000)})
    assert at["required"] is True
    assert at["threshold_applied"] == 50_000 * 100  # ₹50,000 in paise

    below = eway.eway_required({**base, "value": Paise.from_rupees(50_000) - 1})
    assert below["required"] is False

    above = eway.eway_required({**base, "value": Paise.from_rupees(75_000)})
    assert above["required"] is True


# ---- intra-state: pending WS2 pack unless injected ----
def test_intra_state_pending_without_pack():
    cons = {"from_state": "MH", "to_state": "MH", "value": Paise.from_rupees(9_00_000)}
    res = eway.eway_required(cons)
    assert res["required"] is None
    assert res["threshold_applied"] is None
    assert "WS2" in res["reason"]


def test_intra_state_with_injected_threshold():
    # WS2 pack would supply this; here it is injected. ₹1,00,000 intra-state threshold example.
    packs = {"MH": Paise.from_rupees(1_00_000)}
    cons = {"from_state": "MH", "to_state": "MH"}

    at = eway.eway_required(
        {**cons, "value": Paise.from_rupees(1_00_000)}, intra_state_thresholds=packs
    )
    assert at["required"] is True
    assert at["threshold_applied"] == 1_00_000 * 100

    below = eway.eway_required(
        {**cons, "value": Paise.from_rupees(99_999)}, intra_state_thresholds=packs
    )
    assert below["required"] is False


# ---- JSON artifact shape + honesty label ----
def test_build_eway_json_shape_and_label():
    cons = {
        "from_state": "MH",
        "to_state": "GJ",
        "value": Paise.from_rupees(60_000),
        "doc_no": "INV-1",
        "doc_date": "2026-07-20",
        "from_gstin": "27aapfu0939f1zv",
        "to_gstin": "24aapfu0939f1zv",
        "hsn": "1006",
        "cgst": 0,
        "sgst": 0,
        "igst": Paise.from_rupees(3_000),
        "distance_km": 400,
        "vehicle_no": "MH12AB1234",
    }
    art = eway.build_eway_json(cons)

    required_fields = {
        "supplyType",
        "docType",
        "docNo",
        "docDate",
        "fromGstin",
        "toGstin",
        "fromStateCode",
        "toStateCode",
        "totalValue",
        "itemList",
        "transMode",
        "transDistance",
        "vehicleNo",
        "label",
    }
    assert required_fields <= art.keys()

    assert art["label"] == eway.EWB_PREPARE_LABEL
    assert "not filed with the NIC e-way portal" in art["label"]

    # numeric state codes + rupee-decimal money at the edge, uppercased gstin, DD-MM-YYYY date
    assert art["fromStateCode"] == "27" and art["toStateCode"] == "24"
    assert art["totalValue"] == 60_000.0
    assert art["igstValue"] == 3_000.0
    assert art["fromGstin"] == "27AAPFU0939F1ZV"
    assert art["docDate"] == "20-07-2026"
    assert art["itemList"][0]["hsnCode"] == "1006"
