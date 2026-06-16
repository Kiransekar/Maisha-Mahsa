"""Rule IDs this module owns. Authoritative logic lives in `dif/rules/rules.yaml`."""

REVENUE_RULES = {
    "REVENUE-001": "e-Invoice (IRN) missing while turnover exceeds ₹5 crore.",
    "REVENUE-002": "Receivables concentrated in a single customer (>40%).",
}
