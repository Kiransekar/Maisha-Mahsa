"""Server-side RBAC role model + policy layer (WS5.1).

The whole model is **data + one pure predicate**. ``can(role, capability, context)`` answers a
single question: may a principal *in this role* perform an action requiring *this capability*?

§0.8 SECURITY — the ``role`` passed to :func:`can` is ALWAYS the role bound to the authenticated
SESSION/verified context (a Supabase JWT claim once WS4.3 lands), NEVER a value read from a
request body. A request body may say "role=Owner"; it is ignored. This module deliberately has no
knowledge of requests — it is pure so that the only way to reach a capability is through the
session role the auth layer resolved.

Roles (WS5.1):
  Owner       — full control.
  Admin       — full control except the investor-report surface.
  Accountant  — records + audit view + export; NO money/filing approvals, NO user management.
  Approver     — approves payments/filings (subject to the WS5.2 approval *matrix* — amount/action
                 limits live there, not here); read + audit view only otherwise.
  CA          — read-only: Audit Room, queries, exported registers (payroll shows as registers).
  Investor    — time-boxed, watermarked, report-scoped link. Only ``invest_view``, and only inside
                 its window and declared report scope (see :class:`InvestorContext`).

PRODUCT-CONFIRMABLE (§0.6): the exact role→capability assignment below is a sensible default, not a
statutory value. The *architecture* (capability keys + data matrix + pure predicate) is fixed; the
specific rows (e.g. whether Approver may ``export``) are a product decision and can be tuned by
editing :data:`ROLE_CAPABILITIES` without touching the predicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    CA = "ca"
    INVESTOR = "investor"


class Capability(StrEnum):
    READ = "read"
    WRITE = "write"
    APPROVE_PAYMENT = "approve_payment"
    APPROVE_FILING = "approve_filing"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT = "view_audit"
    EXPORT = "export"
    INVEST_VIEW = "invest_view"


# The policy AS DATA. Editing a row re-defines the policy with no code change (and the matrix test
# will fail until the expected table is updated to match — that is the point).
ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.OWNER: frozenset(Capability),  # every capability
    Role.ADMIN: frozenset(
        {
            Capability.READ,
            Capability.WRITE,
            Capability.APPROVE_PAYMENT,
            Capability.APPROVE_FILING,
            Capability.MANAGE_USERS,
            Capability.VIEW_AUDIT,
            Capability.EXPORT,
        }
    ),
    Role.ACCOUNTANT: frozenset(
        {Capability.READ, Capability.WRITE, Capability.VIEW_AUDIT, Capability.EXPORT}
    ),
    Role.APPROVER: frozenset(
        {
            Capability.READ,
            Capability.APPROVE_PAYMENT,
            Capability.APPROVE_FILING,
            Capability.VIEW_AUDIT,
        }
    ),
    Role.CA: frozenset({Capability.READ, Capability.VIEW_AUDIT, Capability.EXPORT}),
    Role.INVESTOR: frozenset({Capability.INVEST_VIEW}),
}


@dataclass(frozen=True)
class InvestorContext:
    """The three constraints a shared investor link carries (WS5.1): time-box, watermark, scope.

    ``now`` is injected (§ determinism) — the predicate never reads the clock. ``watermark`` is
    carried for the renderer to stamp onto every page/export; it does not gate access.
    """

    now: datetime
    not_before: datetime
    not_after: datetime
    report_scope: frozenset[str]
    requested_report: str
    watermark: str

    def permits(self) -> bool:
        """True iff inside the time-box AND the requested report is within the granted scope."""
        in_window = self.not_before <= self.now <= self.not_after
        return in_window and self.requested_report in self.report_scope


def can(role: Role, capability: Capability, context: InvestorContext | None = None) -> bool:
    """May a principal in ``role`` exercise ``capability``? Pure.

    ``role`` is the SESSION role (§0.8), never request-supplied. For the investor link,
    ``invest_view`` additionally requires a valid :class:`InvestorContext` (in-window + in-scope);
    without it, or outside those bounds, access is denied.
    """
    if capability not in ROLE_CAPABILITIES.get(role, frozenset()):
        return False
    if role is Role.INVESTOR and capability is Capability.INVEST_VIEW:
        return isinstance(context, InvestorContext) and context.permits()
    return True


def role_change_event(
    *,
    timestamp: str,
    actor_user_id: str,
    target_user_id: str,
    old_role: Role,
    new_role: Role,
    rules_version: str = "rbac.2026.1",
) -> dict[str, object]:
    """The audit payload for a role change, ready to be chained by ``audit_store.append``.

    Pure: returns the payload, chains nothing (wiring into the live store is WS5.2/integration).
    Shape matches :func:`app.core.audit.make_entry`. No PII — only opaque user ids and role names.
    """
    return {
        "timestamp": timestamp,
        "action": "rbac.role_change",
        "domain": "rbac",
        "user_id": actor_user_id,
        "query": f"{target_user_id}: {old_role.value} -> {new_role.value}",
        "intent_global": None,
        "intent_domain": None,
        "validation_status": "green",
        "rules_version": rules_version,
    }
