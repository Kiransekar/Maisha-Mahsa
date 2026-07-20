"""WS1.D7 — e-way bill threshold engine + compliant JSON artifact.

Two jobs:

* ``eway_required`` — decide whether an e-way bill is mandated for a consignment.
* ``build_eway_json`` — assemble the NIC EWB Part-A/Part-B JSON for one consignment.

Statutory truth (§0.6): the **inter-state** trigger of ₹50,000 consignment value is the
only threshold stated in WS1.D7, so it lives here as a constant. **Intra-state** thresholds
vary per state (some states use ₹1,00,000, some ₹50,000, some exempt certain goods) and come
from the WS2 ``states/<code>.yaml`` packs, which do NOT exist yet. Until they do, an intra-state
consignment's threshold is taken from an injected ``intra_state_thresholds`` map; absent that,
the decision is returned as pending (BLOCKED-CA / WS2) rather than guessed.

Every artifact is a *preparation* aid only — it is not filed with the NIC portal and carries the
prepare-and-download label so a human never mistakes it for a generated e-way bill. Money is paise.
"""

from __future__ import annotations

from typing import Any

from .gst_calc import _STATE_CODES, _to_ddmmyyyy, _to_rupees

# WS1.D7: e-way bill required for inter-state movement when consignment value ≥ ₹50,000.
INTER_STATE_THRESHOLD_PAISE = 50_000 * 100

# Shown on every artifact and every eway_required reason so a draft is never mistaken for filed.
EWB_PREPARE_LABEL = (
    "PREPARE-AND-DOWNLOAD — not filed with the NIC e-way portal; "
    "not a valid e-way bill until generated there"
)


def _is_inter_state(consignment: dict[str, Any]) -> bool:
    """Inter-state when the from/to state codes differ (case-insensitive 2-letter codes)."""
    frm = (consignment.get("from_state") or "").upper()
    to = (consignment.get("to_state") or "").upper()
    return frm != to


def eway_required(
    consignment: dict[str, Any],
    intra_state_thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Decide whether an e-way bill is mandated for ``consignment``.

    ``consignment`` needs at least ``value`` (paise), ``from_state`` and ``to_state`` (2-letter
    codes). ``intra_state_thresholds`` maps a from-state code → its intra-state threshold in paise
    (from the WS2 state pack); ``None`` or a missing state means the intra threshold is unknown.

    Returns ``{required, threshold_applied, reason}``. ``required`` / ``threshold_applied`` are
    ``None`` when the intra-state threshold is not yet available (dependency: WS2 state packs).
    """
    value = int(consignment.get("value", 0))

    if _is_inter_state(consignment):
        threshold = INTER_STATE_THRESHOLD_PAISE
        required = value >= threshold
        return {
            "required": required,
            "threshold_applied": threshold,
            "reason": (
                f"inter-state movement; value ₹{_to_rupees(value):,.2f} "
                f"{'≥' if required else '<'} ₹{_to_rupees(threshold):,.2f} threshold"
            ),
        }

    # Intra-state: threshold is per-state and comes from the WS2 pack.
    state = (consignment.get("from_state") or "").upper()
    threshold = (intra_state_thresholds or {}).get(state)  # type: ignore[assignment]
    if threshold is None:
        return {
            "required": None,
            "threshold_applied": None,
            "reason": (
                f"intra-state movement in {state or '?'}; intra-state threshold pending "
                "WS2 state pack (BLOCKED-CA) — inject intra_state_thresholds to decide"
            ),
        }
    threshold = int(threshold)
    required = value >= threshold
    return {
        "required": required,
        "threshold_applied": threshold,
        "reason": (
            f"intra-state movement in {state}; value ₹{_to_rupees(value):,.2f} "
            f"{'≥' if required else '<'} ₹{_to_rupees(threshold):,.2f} state threshold"
        ),
    }


def build_eway_json(consignment: dict[str, Any]) -> dict[str, Any]:
    """Assemble the NIC e-way-bill JSON (Part-A supply/doc/party/item + Part-B transport) for one
    consignment. Amounts are rupee decimals at the edge; the artifact carries the prepare-and-
    download label. Fields not supplied default to empty — this is a preparation payload, not a
    validated portal submission.
    """
    frm = (consignment.get("from_state") or "").upper()
    to = (consignment.get("to_state") or "").upper()
    value = int(consignment.get("value", 0))

    return {
        "label": EWB_PREPARE_LABEL,
        # Part-A — supply & document
        "supplyType": consignment.get("supply_type", "O"),  # O outward / I inward
        "subSupplyType": consignment.get("sub_supply_type", "1"),  # 1 = Supply
        "docType": consignment.get("doc_type", "INV"),
        "docNo": consignment.get("doc_no", ""),
        "docDate": _to_ddmmyyyy(consignment["doc_date"]) if consignment.get("doc_date") else "",
        # parties
        "fromGstin": (consignment.get("from_gstin") or "").upper(),
        "fromTrdName": consignment.get("from_name", ""),
        "fromPincode": consignment.get("from_pincode"),
        "fromStateCode": _STATE_CODES.get(frm, frm),
        "toGstin": (consignment.get("to_gstin") or "URP").upper(),
        "toTrdName": consignment.get("to_name", ""),
        "toPincode": consignment.get("to_pincode"),
        "toStateCode": _STATE_CODES.get(to, to),
        # value & items
        "totalValue": _to_rupees(value),
        "cgstValue": _to_rupees(consignment.get("cgst", 0)),
        "sgstValue": _to_rupees(consignment.get("sgst", 0)),
        "igstValue": _to_rupees(consignment.get("igst", 0)),
        "itemList": [
            {
                "productName": consignment.get("product_name", ""),
                "hsnCode": consignment.get("hsn", ""),
                "quantity": consignment.get("quantity", 1),
                "qtyUnit": consignment.get("qty_unit", "NOS"),
                "taxableAmount": _to_rupees(consignment.get("taxable", value)),
            }
        ],
        # Part-B — transport
        "transMode": consignment.get("trans_mode", "1"),  # 1 Road 2 Rail 3 Air 4 Ship
        "transDistance": consignment.get("distance_km", 0),
        "transporterId": consignment.get("transporter_id", ""),
        "transDocNo": consignment.get("trans_doc_no", ""),
        "transDocDate": (
            _to_ddmmyyyy(consignment["trans_doc_date"]) if consignment.get("trans_doc_date") else ""
        ),
        "vehicleNo": consignment.get("vehicle_no", ""),
        "vehicleType": consignment.get("vehicle_type", "R"),  # R Regular / O ODC
    }
