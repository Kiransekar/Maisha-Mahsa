"""WS5.2 — approval-matrix tests: Basics/Startup fixed defaults, Growth-configurable matrix,
and the statutory-filing hard rule that no config can lower.

Every case below can genuinely fail: amounts are chosen either side of the real thresholds,
and the filing negative uses a config that actively TRIES to grant a lower role sign-off.
"""

import pytest

from app.core.approval_matrix import DEFAULT_MATRIX, STATUTORY_FILING_ACTIONS, decide_approval
from app.core.rbac import Role

_PAYMENT = "vendor_payment"  # not a statutory-filing action
_FILING = "gstr3b"  # a real member of STATUTORY_FILING_ACTIONS


def test_filing_action_is_a_real_registry_member():
    # guards against the constant drifting empty and every filing-branch test vacuously passing
    assert _FILING in STATUTORY_FILING_ACTIONS
    assert len(STATUTORY_FILING_ACTIONS) > 5


# --- Basics/Startup: fixed default matrix, matrix_config ignored -----------------------------


@pytest.mark.parametrize("plan", ["basics", "startup"])
def test_fixed_plans_use_default_approver_limit(plan):
    within = decide_approval(plan, Role.APPROVER, _PAYMENT, DEFAULT_MATRIX[Role.APPROVER])
    assert within == {
        "required_role_ok": True,
        "needs_approval": False,
        "reason": (
            f"within role limit ({DEFAULT_MATRIX[Role.APPROVER]} <= "
            f"{DEFAULT_MATRIX[Role.APPROVER]} paise, default matrix)"
        ),
    }

    over = decide_approval(plan, Role.APPROVER, _PAYMENT, DEFAULT_MATRIX[Role.APPROVER] + 1)
    assert over["required_role_ok"] is False
    assert over["needs_approval"] is True
    assert "exceeds role limit" in over["reason"]


@pytest.mark.parametrize("plan", ["basics", "startup"])
def test_fixed_plans_ignore_a_supplied_matrix_config(plan):
    # A config that would grant Approver an unlimited ceiling must be IGNORED on Basics/Startup.
    generous_config = {Role.APPROVER: 10**12}
    huge_amount = DEFAULT_MATRIX[Role.APPROVER] + 1
    d = decide_approval(plan, Role.APPROVER, _PAYMENT, huge_amount, matrix_config=generous_config)
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "default matrix" in d["reason"]


def test_accountant_cannot_approve_payments_on_any_fixed_plan():
    d = decide_approval("basics", Role.ACCOUNTANT, _PAYMENT, 1)
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "lacks the approve_payment capability" in d["reason"]


def test_owner_and_admin_unlimited_on_fixed_plans():
    for role in (Role.OWNER, Role.ADMIN):
        d = decide_approval("startup", role, _PAYMENT, 10**11)
        assert d == {"required_role_ok": True, "needs_approval": False, "reason": d["reason"]}
        assert "within role limit" in d["reason"]


# --- Growth: honours a supplied role x amount x action config --------------------------------


def test_growth_honours_supplied_config_tighter_than_default():
    tight_config = {Role.APPROVER: 5_000_00, Role.OWNER: 2**63 - 1, Role.ADMIN: 2**63 - 1}

    # An amount the DEFAULT matrix would clear for Approver, but the org's own config forbids.
    amount = 5_000_01
    assert amount <= DEFAULT_MATRIX[Role.APPROVER]  # would have passed under the default
    d = decide_approval("growth", Role.APPROVER, _PAYMENT, amount, matrix_config=tight_config)
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "configured matrix" in d["reason"]

    # Just inside the tighter configured limit → clears.
    d_ok = decide_approval("growth", Role.APPROVER, _PAYMENT, 5_000_00, matrix_config=tight_config)
    assert d_ok["required_role_ok"] is True
    assert d_ok["needs_approval"] is False


def test_growth_honours_supplied_config_looser_than_default():
    loose_config = {Role.APPROVER: 10**10}
    amount = DEFAULT_MATRIX[Role.APPROVER] + 1  # would have failed under the default
    d = decide_approval("growth", Role.APPROVER, _PAYMENT, amount, matrix_config=loose_config)
    assert d["required_role_ok"] is True
    assert d["needs_approval"] is False
    assert "configured matrix" in d["reason"]


def test_growth_falls_back_to_default_matrix_when_unconfigured():
    d = decide_approval("growth", Role.APPROVER, _PAYMENT, DEFAULT_MATRIX[Role.APPROVER] + 1)
    assert d["required_role_ok"] is False
    assert "default matrix" in d["reason"]


def test_growth_config_role_with_no_entry_denied():
    # a Growth org's own matrix that simply forgot to give Approver a row
    d = decide_approval("growth", Role.APPROVER, _PAYMENT, 1, matrix_config={Role.OWNER: 10**12})
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "no limit in the configured matrix" in d["reason"]


# --- The security-critical negative: statutory filing ALWAYS needs Owner/Admin ---------------


def test_statutory_filing_requires_owner_or_admin_on_every_plan():
    for plan in ("basics", "startup", "growth"):
        for role in (Role.OWNER, Role.ADMIN):
            d = decide_approval(plan, role, _FILING, 1)
            assert d["required_role_ok"] is True
            assert d["needs_approval"] is False


def test_statutory_filing_denies_approver_even_though_approver_can_approve_payments():
    # Approver has APPROVE_FILING capability under rbac.can() (WS5.1) — but WS5.2's matrix
    # still denies it here: the filing hard rule is Owner/Admin ONLY, not "anyone with the cap".
    d = decide_approval("basics", Role.APPROVER, _FILING, 1)
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "Owner or Admin" in d["reason"]


def test_statutory_filing_cannot_be_lowered_by_a_growth_config():
    # The config actively TRIES to let Approver clear an enormous filing amount. It must be
    # ignored: this is the one thing a matrix_config cannot do, per the ticket's hard rule.
    lowering_config = {Role.APPROVER: 2**63 - 1, Role.OWNER: 2**63 - 1, Role.ADMIN: 2**63 - 1}
    d = decide_approval("growth", Role.APPROVER, _FILING, 10**9, matrix_config=lowering_config)
    assert d["required_role_ok"] is False
    assert d["needs_approval"] is True
    assert "cannot be configured away" in d["reason"] or "Owner or Admin" in d["reason"]

    # Meanwhile Owner still clears it under the very same config, on the very same plan.
    d_owner = decide_approval("growth", Role.OWNER, _FILING, 10**9, matrix_config=lowering_config)
    assert d_owner["required_role_ok"] is True
    assert d_owner["needs_approval"] is False


def test_accountant_and_ca_never_clear_a_filing():
    for role in (Role.ACCOUNTANT, Role.CA, Role.INVESTOR):
        d = decide_approval("growth", role, _FILING, 1)
        assert d["required_role_ok"] is False
        assert d["needs_approval"] is True


# --- input validation ---------------------------------------------------------------------


def test_unknown_plan_rejected():
    with pytest.raises(ValueError):
        decide_approval("enterprise", Role.OWNER, _PAYMENT, 1)


def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        decide_approval("basics", Role.OWNER, _PAYMENT, -1)


def test_zero_amount_boundary_is_allowed():
    d = decide_approval("basics", Role.APPROVER, _PAYMENT, 0)
    assert d["required_role_ok"] is True
    assert d["needs_approval"] is False
