"""WS5.3 — per-role landing + vault-sensitivity clearance on the canonical Role model."""

from app.core.landing import (
    ROLE_CLEARANCE,
    ROLE_LANDING,
    can_view_sensitivity,
    default_landing,
)
from app.core.rbac import Role


def test_every_role_has_a_landing_and_clearance():
    for role in Role:
        assert role in ROLE_LANDING
        assert role in ROLE_CLEARANCE


def test_spec_named_landings():
    assert default_landing(Role.OWNER) == "today"
    assert default_landing(Role.ACCOUNTANT) == "exception_inbox"
    assert default_landing(Role.CA) == "audit_room"


def test_owner_sees_everything_investor_is_report_scoped():
    for s in ("public", "internal", "confidential", "restricted"):
        assert can_view_sensitivity(Role.OWNER, s) is True
    # investor: internal at most — no confidential/restricted vault docs
    assert can_view_sensitivity(Role.INVESTOR, "internal") is True
    assert can_view_sensitivity(Role.INVESTOR, "confidential") is False
    assert can_view_sensitivity(Role.INVESTOR, "restricted") is False


def test_ca_and_accountant_stop_below_restricted():
    # CA/Accountant see confidential (payslips/contracts) but NOT restricted founder/cap-table docs
    for role in (Role.CA, Role.ACCOUNTANT, Role.APPROVER):
        assert can_view_sensitivity(role, "confidential") is True
        assert can_view_sensitivity(role, "restricted") is False


def test_unknown_sensitivity_is_fail_closed():
    # an unrecognised class is treated as most-restricted -> only Owner/Admin clear it
    assert can_view_sensitivity(Role.OWNER, "top_secret") is True
    assert can_view_sensitivity(Role.CA, "top_secret") is False
