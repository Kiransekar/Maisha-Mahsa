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

import re
from typing import Any

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


# Vault sensitivity classes, least → most restricted (matches vault_calc's class names, plus
# T11's salary_detail: per-employee pay figures — above confidential because the CA/Approver
# seats that may read payslip *documents* workflows still must not get raw pay figures in every
# JSON payload, below restricted because the Accountant who runs payroll must see them).
SENSITIVITY_ORDER: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "salary_detail": 3,
    "restricted": 4,
}

# The highest sensitivity class each role may view. Owner/Admin see everything; the Accountant
# additionally clears salary_detail (they run payroll); CA/Approver see up to confidential
# (payslips, contracts) but NOT per-employee salary payloads or restricted founder/cap-table/
# board docs; Investor is report-scoped (internal at most — no margin/unit-economics).
# Product-confirmable defaults.
ROLE_CLEARANCE: dict[Role, str] = {
    Role.OWNER: "restricted",
    Role.ADMIN: "restricted",
    Role.ACCOUNTANT: "salary_detail",
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


# ── T11: field-level RBAC payload masking ────────────────────────────────────────────────────
# One clearance system: the SAME lattice + ``can_view_sensitivity`` above, applied to individual
# payload fields at the serialization boundary. The map below names the sensitive field keys
# conservatively (per-employee salary; margin/unit-economics); everything unnamed passes through.

#: Per-employee payroll figure targets — ``emp{id}.net_pay`` / ``.pf_employee`` / … (the shape
#: app/web/api_payroll.py mints). Any per-employee figure is salary detail.
_PER_EMPLOYEE_TARGET = re.compile(r"^emp\d+\.")

#: Exact field key → sensitivity class. salary_detail → Owner/Admin/Accountant only;
#: confidential → everyone but Investor (margin/unit-economics never leave via a report link).
FIELD_SENSITIVITY: dict[str, str] = {
    "monthly_net_paise": "salary_detail",  # runs_overview per-employee net
    "gross_margin": "confidential",
    "cac": "confidential",
    "ltv": "confidential",
    "payback_months": "confidential",
    "ltv_cac_ratio": "confidential",
}


def field_sensitivity(key: str) -> str | None:
    """The sensitivity class of a payload field key, or None if the field is not sensitive."""
    if _PER_EMPLOYEE_TARGET.match(key):
        return "salary_detail"
    return FIELD_SENSITIVITY.get(key)


#: What replaces a masked field. The value is GONE from the body, never dimmed or zeroed —
#: and the reason names the missing clearance so the SPA can say why (hidden-not-absent
#: violates the WS7 contract's visibility rule).
def _restricted(sensitivity: str) -> dict[str, Any]:
    return {"restricted": True, "reason": f"requires {sensitivity} clearance"}


def mask_field(role: Role, key: str, payload: Any) -> Any:
    """THE masking helper (T11) — every /api assembler serializing a sensitive field calls this.

    Returns ``payload`` unchanged when ``key`` is not sensitive or ``role`` is cleared for it
    (``can_view_sensitivity`` — the one clearance system). Otherwise returns
    ``{"restricted": true, "reason": "requires <class> clearance"}`` carrying over only the
    identifying keys a UI needs to label the lock chip — NEVER any value-bearing key
    (``value_paise``, ``raw``, ``working`` inputs, …)."""
    sensitivity = field_sensitivity(key)
    if sensitivity is None or can_view_sensitivity(role, sensitivity):
        return payload
    masked = _restricted(sensitivity)
    if isinstance(payload, dict):
        for keep in ("target", "key", "label"):
            if keep in payload:
                masked[keep] = payload[keep]
    return masked


def mask_figures(role: Role, figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``mask_field`` over a badged-figure list (each figure keyed by its own target/key)."""
    return [mask_field(role, str(f.get("target") or f.get("key") or ""), f) for f in figures]
