"""Per-role landing surfaces + vault-sensitivity clearance wired to the canonical RBAC roles
(MMX-1.0 §WS5.3). Pure policy data; the surface/role come from the SESSION (§0.8), never a
request body. No router wiring here (that arrives with WS4.3 auth + WS7 UI).

The landing map is the §WS7.4 per-role default surface. The clearance map replaces the vault's
legacy standalone role ranks (app/domains/vault/vault_calc.py) with the canonical Role model —
vault access should route through ``can_view_sensitivity`` once the vault is org-scoped (WS4.2).
Both maps are product-confirmable defaults (§0.6): the mechanism is fixed, the exact assignments
are a product decision.
"""

from __future__ import annotations

from app.core.rbac import Role

# §WS7.4 default landing surface per role (a remembered toggle can override at runtime).
ROLE_LANDING: dict[Role, str] = {
    Role.OWNER: "today",
    Role.ADMIN: "today",
    Role.ACCOUNTANT: "exception_inbox",
    Role.APPROVER: "exception_inbox",
    Role.CA: "audit_room",
    Role.INVESTOR: "investor_report",
}


def default_landing(role: Role) -> str:
    """The surface a role lands on by default. Owner→Today, Accountant→Exception Inbox,
    CA→Audit Room (§WS5.3/§WS7.4)."""
    return ROLE_LANDING[role]


# Vault sensitivity classes, least → most restricted (matches vault_calc's class names).
SENSITIVITY_ORDER: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}

# The highest sensitivity class each role may view. Owner/Admin see everything; CA/Accountant/
# Approver see up to confidential (payslips, contracts) but NOT restricted founder/cap-table/board
# docs by default; Investor is report-scoped (internal at most). Product-confirmable defaults.
ROLE_CLEARANCE: dict[Role, str] = {
    Role.OWNER: "restricted",
    Role.ADMIN: "restricted",
    Role.ACCOUNTANT: "confidential",
    Role.APPROVER: "confidential",
    Role.CA: "confidential",
    Role.INVESTOR: "internal",
}


def role_clearance(role: Role) -> str:
    return ROLE_CLEARANCE[role]


def can_view_sensitivity(role: Role, sensitivity: str) -> bool:
    """True iff ``role`` is cleared for a document of ``sensitivity`` (§WS5.3). Unknown
    sensitivity is treated as the most restricted → fail-closed."""
    need = SENSITIVITY_ORDER.get(sensitivity, max(SENSITIVITY_ORDER.values()))
    return need <= SENSITIVITY_ORDER[ROLE_CLEARANCE[role]]
