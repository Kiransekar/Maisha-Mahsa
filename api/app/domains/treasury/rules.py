"""Rule IDs this module owns. The authoritative logic lives in `dif/rules/rules.yaml`
(evaluated by Mahsa); this mirror exists so the Python side can reference/test rule
coverage and surface citations in the UI."""

TREASURY_RULES = {
    "TREASURY-001": "Cash runway below 3 months — block discretionary spend.",
}
