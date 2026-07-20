"""WS5.1 permission-matrix test: every role x every capability, allow/deny asserted explicitly.

The EXPECTED table below is written out by hand (independent of ``ROLE_CAPABILITIES``) so this
test can actually FAIL: change a row in the source matrix and the corresponding cell here stops
matching. The investor cells assume a valid in-window/in-scope context — its gating is exercised
separately.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.rbac import (
    Capability,
    InvestorContext,
    Role,
    can,
    role_change_event,
)

# Independent ground truth: role -> {capability: allowed?}. Every role x every capability.
T, F = True, False
EXPECTED: dict[Role, dict[Capability, bool]] = {
    Role.OWNER: {
        Capability.READ: T, Capability.WRITE: T, Capability.APPROVE_PAYMENT: T,
        Capability.APPROVE_FILING: T, Capability.MANAGE_USERS: T, Capability.VIEW_AUDIT: T,
        Capability.EXPORT: T, Capability.INVEST_VIEW: T,
    },
    Role.ADMIN: {
        Capability.READ: T, Capability.WRITE: T, Capability.APPROVE_PAYMENT: T,
        Capability.APPROVE_FILING: T, Capability.MANAGE_USERS: T, Capability.VIEW_AUDIT: T,
        Capability.EXPORT: T, Capability.INVEST_VIEW: F,
    },
    Role.ACCOUNTANT: {  # NO money/filing approvals, NO user management
        Capability.READ: T, Capability.WRITE: T, Capability.APPROVE_PAYMENT: F,
        Capability.APPROVE_FILING: F, Capability.MANAGE_USERS: F, Capability.VIEW_AUDIT: T,
        Capability.EXPORT: T, Capability.INVEST_VIEW: F,
    },
    Role.APPROVER: {  # approves, but does not author records or manage users
        Capability.READ: T, Capability.WRITE: F, Capability.APPROVE_PAYMENT: T,
        Capability.APPROVE_FILING: T, Capability.MANAGE_USERS: F, Capability.VIEW_AUDIT: T,
        Capability.EXPORT: F, Capability.INVEST_VIEW: F,
    },
    Role.CA: {  # read-only: audit room + queries + exported registers
        Capability.READ: T, Capability.WRITE: F, Capability.APPROVE_PAYMENT: F,
        Capability.APPROVE_FILING: F, Capability.MANAGE_USERS: F, Capability.VIEW_AUDIT: T,
        Capability.EXPORT: T, Capability.INVEST_VIEW: F,
    },
    Role.INVESTOR: {  # only the scoped report, and only inside its window
        Capability.READ: F, Capability.WRITE: F, Capability.APPROVE_PAYMENT: F,
        Capability.APPROVE_FILING: F, Capability.MANAGE_USERS: F, Capability.VIEW_AUDIT: F,
        Capability.EXPORT: F, Capability.INVEST_VIEW: T,
    },
}

_NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _valid_investor_ctx() -> InvestorContext:
    return InvestorContext(
        now=_NOW,
        not_before=_NOW - timedelta(days=1),
        not_after=_NOW + timedelta(days=7),
        report_scope=frozenset({"cap_table", "runway"}),
        requested_report="cap_table",
        watermark="shared with acme-vc · 2026-07-20",
    )


def test_expected_table_covers_every_role_and_capability():
    # Guard against a silently-incomplete matrix (a missing cell would vacuously pass below).
    assert set(EXPECTED) == set(Role)
    for row in EXPECTED.values():
        assert set(row) == set(Capability)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("capability", list(Capability))
def test_permission_matrix(role: Role, capability: Capability):
    ctx = _valid_investor_ctx() if role is Role.INVESTOR else None
    assert can(role, capability, ctx) is EXPECTED[role][capability]


# --- Explicit spec negatives (WS5.1), independent of the parametrized sweep -------------------

def test_accountant_cannot_approve_money_or_filings():
    assert can(Role.ACCOUNTANT, Capability.APPROVE_PAYMENT) is False
    assert can(Role.ACCOUNTANT, Capability.APPROVE_FILING) is False


def test_ca_is_read_only():
    for cap in (Capability.WRITE, Capability.APPROVE_PAYMENT, Capability.APPROVE_FILING,
                Capability.MANAGE_USERS):
        assert can(Role.CA, cap) is False


def test_investor_denied_without_context():
    assert can(Role.INVESTOR, Capability.INVEST_VIEW, None) is False


def test_investor_denied_outside_time_box():
    ctx = _valid_investor_ctx()
    expired = InvestorContext(
        now=ctx.not_after + timedelta(seconds=1),
        not_before=ctx.not_before,
        not_after=ctx.not_after,
        report_scope=ctx.report_scope,
        requested_report=ctx.requested_report,
        watermark=ctx.watermark,
    )
    assert can(Role.INVESTOR, Capability.INVEST_VIEW, expired) is False


def test_investor_denied_outside_report_scope():
    ctx = _valid_investor_ctx()
    out_of_scope = InvestorContext(
        now=ctx.now,
        not_before=ctx.not_before,
        not_after=ctx.not_after,
        report_scope=ctx.report_scope,
        requested_report="full_ledger",  # not in scope
        watermark=ctx.watermark,
    )
    assert can(Role.INVESTOR, Capability.INVEST_VIEW, out_of_scope) is False


def test_investor_allowed_in_window_and_scope():
    assert can(Role.INVESTOR, Capability.INVEST_VIEW, _valid_investor_ctx()) is True


def test_role_change_event_is_audit_chainable_and_pii_free():
    ev = role_change_event(
        timestamp="2026-07-20T00:00:00+00:00",
        actor_user_id="u_owner",
        target_user_id="u_42",
        old_role=Role.ACCOUNTANT,
        new_role=Role.APPROVER,
    )
    # shape matches app.core.audit.make_entry's required keys
    from app.core.audit import GENESIS_HASH, make_entry

    entry = make_entry(GENESIS_HASH, ev)
    assert entry.action == "rbac.role_change"
    assert entry.domain == "rbac"
    assert ev["query"] == "u_42: accountant -> approver"
