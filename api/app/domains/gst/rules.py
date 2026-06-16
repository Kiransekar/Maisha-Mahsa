"""Rule IDs this module owns. Authoritative logic lives in `dif/rules/rules.yaml`."""

GST_RULES = {
    "GST-001": "GSTR-3B filed/paid after the 20th — late fee accrues.",
    "GST-002": "ITC claimed exceeds 105% of GSTR-2B (Rule 36(4)).",
    "GST-003": "GSTR-1 outward tax does not match GSTR-3B (liability mismatch).",
}
