"""WS6.1 — entitlement architecture tests (full matrix + statutory grace).

Every assertion here exercises real registry/plan data and can genuinely fail if the
split, the grace override, or the visibility contract regress.
"""

import logging

import pytest

from app.core import entitlements as ent

# --- split counts ------------------------------------------------------------


def test_split_counts_are_71_34_11_totalling_116():
    counts = ent.plan_counts()
    assert counts == {"basics": 71, "startup_adds": 34, "growth_adds": 11}
    assert sum(counts.values()) == 116
    # the registry's domain space is exactly those 116 features
    assert len(ent.DOMAIN_FEATURES) == 116


def test_plans_partition_the_registry_exactly():
    # validate_registry() already runs at import; assert it stays green explicitly
    ent.validate_registry()
    assert len(ent._PLAN_FEATURES["growth"]) == 116  # Growth = all domain features


# --- full matrix: entitlement resolves correctly across all plans ------------

# (feature, entitled-on-basics?, entitled-on-startup?, entitled-on-growth?)
_MATRIX = [
    ("cash_position", True, True, True),  # Basics feature
    ("gstr3b", True, True, True),  # Basics
    ("cap_table", False, True, True),  # Startup-only
    ("itr", False, True, True),  # Startup-only (also statutory)
    ("transfer_pricing", False, False, True),  # Growth-only
    ("rights_buyback", False, False, True),  # Growth-only
    ("secretarial", False, False, True),  # Growth-only
    ("platform.dashboard", True, True, True),  # platform baseline, every plan
]


@pytest.mark.parametrize("feature,on_basics,on_startup,on_growth", _MATRIX)
def test_entitlement_matrix(feature, on_basics, on_startup, on_growth):
    assert ent.is_entitled("basics", feature) is on_basics
    assert ent.is_entitled("startup", feature) is on_startup
    assert ent.is_entitled("growth", feature) is on_growth


def test_growth_only_feature_denied_on_basics():
    assert ent.is_entitled("basics", "transfer_pricing") is False
    assert ent.is_entitled("growth", "transfer_pricing") is True


def test_cumulative_startup_includes_all_basics():
    for f in ent._LAYERS["basics"]:
        assert ent.is_entitled("startup", f) and ent.is_entitled("growth", f)


def test_unknown_plan_rejected():
    with pytest.raises(ValueError):
        ent.is_entitled("enterprise", "gstr3b")


# --- statutory-grace override ------------------------------------------------


def test_statutory_filing_allowed_on_basics_with_grace_and_upsell(caplog):
    # `itr` is a Startup feature AND a statutory filing → never blocked on Basics.
    assert ent.is_entitled("basics", "itr") is False  # not entitled...

    with caplog.at_level(logging.INFO, logger="maisha.entitlements"):
        d = ent.guard("basics", "itr")

    assert d.allowed is True  # ...but the filing is allowed (grace)
    assert d.grace is True
    assert d.upsell == "startup"  # upsell recorded for after the flow
    assert "statutory" in d.reason.lower()
    # the grace event is logged (keys only, no PII)
    assert any("statutory_grace" in r.getMessage() for r in caplog.records)
    assert any("feature=itr" in r.getMessage() for r in caplog.records)


def test_non_statutory_locked_feature_is_denied_but_visible_with_reason():
    d = ent.guard("basics", "transfer_pricing")
    assert d.allowed is False
    assert d.grace is False
    assert d.visible is True  # NEVER hidden
    assert d.upsell == "growth"
    assert "growth" in d.reason.lower()


def test_entitled_feature_guard_allows_without_upsell():
    d = ent.guard("basics", "gstr3b")
    assert d.allowed and not d.grace and d.upsell is None and d.visible


# --- quantity-gate stub ------------------------------------------------------


def test_quantity_gate_soft_warn_grace_block_progression():
    # headcount limit on Basics is 10 (fair-use tiers 10/50/200)
    assert ent.quantity_gate("headcount", 5, "basics").state is ent.GateState.OK
    assert ent.quantity_gate("headcount", 9, "basics").state is ent.GateState.SOFT_WARN
    assert ent.quantity_gate("headcount", 11, "basics").state is ent.GateState.GRACE
    blocked = ent.quantity_gate("headcount", 40, "basics")
    assert blocked.state is ent.GateState.BLOCK
    assert blocked.visible is True  # ceiling shown, not hidden
    assert blocked.upsell == "startup"  # Startup clears 40 headcount


# --- §0.8: plan comes from session context, never a request body -------------


def test_plan_from_context_reads_session_only():
    assert ent.plan_from_context({"org_plan": "growth"}) == "growth"

    class Sess:
        org_plan = "startup"

    assert ent.plan_from_context(Sess()) == "startup"

    with pytest.raises(ValueError):
        ent.plan_from_context({"plan_from_body": "growth"})  # no valid session plan → refuse
