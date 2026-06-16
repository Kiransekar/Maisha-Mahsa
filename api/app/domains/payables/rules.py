"""Rule IDs this module owns. Authoritative logic lives in `dif/rules/rules.yaml`."""

PAYABLES_RULES = {
    "PAYABLES-001": "MSME vendor unpaid beyond 45 days (MSMED Act / s.43B(h)).",
    "PAYABLES-002": "Bill cleared with a PO 3-way-match variance beyond 5%.",
}
