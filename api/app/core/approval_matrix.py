"""WS5.2 — Approval matrices: a pure role x amount x action decision.

Kept SEPARATE from :mod:`app.core.approvals` (the F4 Mahsa-driven approval QUEUE —
``ApprovalItem``/``pending_approvals``/``record_decision``, all DB+Mahsa+audit-chain wired).
That module's working API is untouched. This module answers a narrower, pure question with no
DB/Mahsa dependency: "may THIS role approve THIS action of THIS amount, on THIS plan?" —
the role x amount x action matrix WS5.2 asks for.

Reuses, never re-derives:
  * :func:`app.core.rbac.can` — the role-capability predicate (WS5.1).
  * :mod:`app.core.entitlements` — plan validity (:data:`PLAN_ORDER`) and the statutory-filing
    action universe. ``STATUTORY_GRACE_FEATURES`` (WS6.1) already enumerates every statutory
    filing / statutory-contribution feature (gstr1, itr, pf, mca_filings, ...); WS5.2's
    "statutory-filing action" is the same underlying set, so it is imported rather than
    re-listed a second time.

§0.8 SECURITY: ``role``/``plan`` are values the CALLER resolves from the verified session
context; this module never reads a request body and has no notion of a request at all.

§0.6 PRODUCT-CONFIRMABLE: :data:`DEFAULT_MATRIX` (the Basics/Startup fixed thresholds, and the
Growth fallback when no org config has been set yet) is a sensible starting point, not a
statutory value. Flagged here for product confirmation; does not block WS5.2.

HARD RULE (cannot be configured away): a statutory-filing action ALWAYS requires Owner or Admin,
regardless of ``matrix_config`` — even a config that grants a lower role a huge limit for that
action is ignored on the filing path.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.entitlements import PLAN_ORDER
from app.core.entitlements import STATUTORY_GRACE_FEATURES as STATUTORY_FILING_ACTIONS
from app.core.rbac import Capability, Role, can

__all__ = [
    "STATUTORY_FILING_ACTIONS",
    "DEFAULT_MATRIX",
    "ApprovalDecision",
    "decide_approval",
]

#: Roles that may EVER clear a statutory-filing action — fixed, not data, not configurable.
_FILING_APPROVER_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.ADMIN})

#: PRODUCT-CONFIRMABLE (§0.6) fixed default matrix for Basics/Startup: the highest amount (in
#: integer paise) each role may clear unattended. A role absent from the map cannot approve at
#: all. Growth falls back to this same table until the org supplies its own ``matrix_config``.
DEFAULT_MATRIX: dict[Role, int] = {
    Role.OWNER: 2**63 - 1,  # unlimited
    Role.ADMIN: 2**63 - 1,  # unlimited
    Role.APPROVER: 100_000_00,  # PRODUCT-CONFIRMABLE default: Rs 1,00,000 in paise
}


def _capability_for(action: str) -> Capability:
    return (
        Capability.APPROVE_FILING
        if action in STATUTORY_FILING_ACTIONS
        else Capability.APPROVE_PAYMENT
    )


@dataclass(frozen=True)
class ApprovalDecision:
    required_role_ok: bool
    needs_approval: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "required_role_ok": self.required_role_ok,
            "needs_approval": self.needs_approval,
            "reason": self.reason,
        }


def decide_approval(
    plan: str,
    role: Role,
    action: str,
    amount: int,
    matrix_config: dict[Role, int] | None = None,
) -> dict[str, object]:
    """Pure: may ``role`` clear ``action`` of ``amount`` paise, on ``plan``, unattended?

    Returns ``{"required_role_ok": bool, "needs_approval": bool, "reason": str}``.

    * ``required_role_ok`` — this role, on its own, may clear this action/amount right now.
    * ``needs_approval``   — a (further) approval step is required before this can proceed.
      False only when the role already clears it (``required_role_ok`` True).

    Rules, in order:
      1. Statutory-filing ``action`` (member of ``STATUTORY_FILING_ACTIONS``) → HARD gate:
         only Owner/Admin ever clear it. ``matrix_config`` is never consulted for this action,
         on any plan — this is the one thing WS5.2 says cannot be configured away.
      2. Otherwise: Basics/Startup always use :data:`DEFAULT_MATRIX`. Growth uses a supplied
         ``matrix_config`` (a ``{Role: max_amount_paise}`` map) when given, else the same
         default. Role must have the underlying rbac capability AND a limit covering ``amount``.
    """
    if plan not in PLAN_ORDER:
        raise ValueError(f"unknown plan {plan!r}; expected one of {PLAN_ORDER}")
    if amount < 0:
        raise ValueError("amount must be >= 0 paise")

    capability = _capability_for(action)

    if action in STATUTORY_FILING_ACTIONS:
        role_ok = role in _FILING_APPROVER_ROLES and can(role, capability)
        reason = (
            "statutory filing: Owner/Admin clears it (fixed — cannot be configured away)"
            if role_ok
            else "statutory filing: requires Owner or Admin regardless of matrix_config"
        )
        return ApprovalDecision(
            required_role_ok=role_ok, needs_approval=not role_ok, reason=reason
        ).as_dict()

    matrix, source = DEFAULT_MATRIX, "default"
    if plan == "growth" and matrix_config is not None:
        matrix, source = matrix_config, "configured"

    if not can(role, capability):
        return ApprovalDecision(
            required_role_ok=False,
            needs_approval=True,
            reason=f"role '{role.value}' lacks the {capability.value} capability",
        ).as_dict()

    limit = matrix.get(role)
    if limit is None:
        return ApprovalDecision(
            required_role_ok=False,
            needs_approval=True,
            reason=f"role '{role.value}' has no limit in the {source} matrix",
        ).as_dict()

    if amount <= limit:
        return ApprovalDecision(
            required_role_ok=True,
            needs_approval=False,
            reason=f"within role limit ({amount} <= {limit} paise, {source} matrix)",
        ).as_dict()

    return ApprovalDecision(
        required_role_ok=False,
        needs_approval=True,
        reason=(f"exceeds role limit ({amount} > {limit} paise, {source} matrix) — escalate"),
    ).as_dict()
