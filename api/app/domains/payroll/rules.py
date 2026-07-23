"""Rule IDs this module owns. Authoritative logic lives in `dif/rules/rules.yaml`."""

PAYROLL_RULES = {
    "PAYROLL-001": "PF (EPF) not deposited by the 15th of the following month.",
    "PAYROLL-002": "ESI contribution not deposited by the 15th of the following month.",
    "PAYROLL-003": "A payroll entry has negative net pay.",
    "PAYROLL-004": "Statutory bonus provision under-funded vs the 8-1/3% minimum.",
    "PAYROLL-005": "A drafted payroll run awaits approval before wages are released.",
}
