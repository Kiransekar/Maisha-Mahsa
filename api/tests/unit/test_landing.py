"""WS5.3 — per-role landing + vault-sensitivity clearance on the canonical Role model."""

from app.core.landing import (
    ROLE_CLEARANCE,
    ROLE_LANDING,
    can_view_sensitivity,
    default_landing,
    field_sensitivity,
    mask_field,
    mask_figures,
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


# ── T11 field-level masking (one lattice, one predicate — no second clearance system) ────────


def test_salary_detail_sits_between_confidential_and_restricted():
    # Accountant runs payroll -> cleared; CA/Approver read payslip workflows -> NOT cleared
    for role in (Role.OWNER, Role.ADMIN, Role.ACCOUNTANT):
        assert can_view_sensitivity(role, "salary_detail") is True
    for role in (Role.APPROVER, Role.CA, Role.INVESTOR):
        assert can_view_sensitivity(role, "salary_detail") is False
    # and the Accountant still stops below restricted (founder/cap-table docs)
    assert can_view_sensitivity(Role.ACCOUNTANT, "restricted") is False


def test_field_sensitivity_map():
    assert field_sensitivity("emp7.net_pay") == "salary_detail"  # any per-employee figure
    assert field_sensitivity("monthly_net_paise") == "salary_detail"
    assert field_sensitivity("gross_margin") == "confidential"
    assert field_sensitivity("ltv_cac_ratio") == "confidential"
    assert field_sensitivity("monthly_burn") is None  # aggregates pass through


def test_mask_field_strips_the_value_entirely():
    figure = {
        "target": "emp1.net_pay",
        "label": "Net pay",
        "value_paise": 1_234_567,
        "state": "verified",
        "working": {"inputs": [{"label": "gross (paise)", "value": "9999999"}]},
    }
    masked = mask_field(Role.CA, "emp1.net_pay", figure)
    assert masked == {
        "restricted": True,
        "reason": "requires salary_detail clearance",
        "target": "emp1.net_pay",
        "label": "Net pay",
    }
    # the value is NOT in the masked payload anywhere — not even nested
    assert "1234567" not in str(masked) and "9999999" not in str(masked)
    # a cleared role gets the figure untouched (same object, no re-derivation)
    assert mask_field(Role.ACCOUNTANT, "emp1.net_pay", figure) is figure
    # a non-sensitive key passes through for everyone
    assert mask_field(Role.CA, "monthly_burn", 42) == 42


def test_mask_field_masks_scalars_and_margin_for_investor():
    assert mask_field(Role.CA, "monthly_net_paise", 5_000_00) == {
        "restricted": True,
        "reason": "requires salary_detail clearance",
    }
    assert mask_field(Role.INVESTOR, "ltv_cac_ratio", 3.2) == {
        "restricted": True,
        "reason": "requires confidential clearance",
    }
    # every read-holding role keeps margin figures; only the Investor link loses them
    for role in (Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.APPROVER, Role.CA):
        assert mask_field(role, "ltv_cac_ratio", 3.2) == 3.2


def test_mask_figures_masks_only_the_sensitive_ones():
    figures = [
        {"target": "emp1.pf_employee", "label": "PF", "value_paise": 1800_00},
        {"target": "total_gross", "label": "Total gross", "value_paise": 99_000_00},
        {"key": "monthly_burn", "label": "Monthly burn", "raw": 5},
    ]
    out = mask_figures(Role.APPROVER, figures)
    assert out[0] == {
        "restricted": True,
        "reason": "requires salary_detail clearance",
        "target": "emp1.pf_employee",
        "label": "PF",
    }
    assert out[1] is figures[1] and out[2] is figures[2]
