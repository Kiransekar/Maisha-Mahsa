"""WS6.2 — quantity gate tests (headcount / seats / entities).

Boundary points are derived from the real ``QUANTITY_LIMITS`` data, not hardcoded magic
numbers, so a regression in either the data or the state-machine branches breaks a test.
"""

import math

import pytest

from app.core import entitlements as ent

WARN_RATIO = 0.8
GRACE_BAND = 2

DIMENSIONS = ("headcount", "seats", "entities")


def _points(limit: int) -> dict[str, int]:
    """The four boundary counts that must land in OK / SOFT_WARN / GRACE / BLOCK."""
    return {
        "ok": math.floor(WARN_RATIO * limit),
        "soft_warn": limit,
        "grace": limit + GRACE_BAND,
        "block": limit + GRACE_BAND + 1,
    }


# --- full ok -> soft_warn -> grace -> block progression, per dimension -------


@pytest.mark.parametrize("kind", DIMENSIONS)
def test_full_progression_across_the_basics_ceiling(kind: str) -> None:
    limit = ent.QUANTITY_LIMITS[kind]["basics"]
    pts = _points(limit)

    ok = ent.quantity_gate(kind, pts["ok"], "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND)
    warn = ent.quantity_gate(
        kind, pts["soft_warn"], "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND
    )
    grace = ent.quantity_gate(
        kind, pts["grace"], "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND
    )
    block = ent.quantity_gate(
        kind, pts["block"], "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND
    )

    assert ok.state is ent.GateState.OK
    assert warn.state is ent.GateState.SOFT_WARN
    assert grace.state is ent.GateState.GRACE
    assert block.state is ent.GateState.BLOCK

    # each state is a genuinely different branch, not a coincidence of the fixture
    states = {ok.state, warn.state, grace.state, block.state}
    assert states == {
        ent.GateState.OK,
        ent.GateState.SOFT_WARN,
        ent.GateState.GRACE,
        ent.GateState.BLOCK,
    }


@pytest.mark.parametrize("kind", DIMENSIONS)
def test_block_names_the_upgrade_plan(kind: str) -> None:
    limit = ent.QUANTITY_LIMITS[kind]["basics"]
    block = ent.quantity_gate(
        kind,
        limit + GRACE_BAND + 1,
        "basics",
        warn_ratio=WARN_RATIO,
        grace_band=GRACE_BAND,
    )
    assert block.state is ent.GateState.BLOCK
    assert block.upsell is not None
    assert block.upsell in ent.PLAN_ORDER
    assert block.upsell != "basics"
    # the named plan must actually be able to absorb the count
    assert ent.QUANTITY_LIMITS[kind][block.upsell] >= block.current


def test_block_upgrade_can_skip_a_plan_that_still_cannot_absorb_the_count() -> None:
    # entities: basics=1, startup=3, growth=10 — a block at current=4 must skip
    # startup (3 < 4) and name growth, not just "the next plan up".
    block = ent.quantity_gate("entities", 4, "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND)
    assert block.state is ent.GateState.BLOCK
    assert block.upsell == "growth"


@pytest.mark.parametrize("kind", DIMENSIONS)
def test_grace_is_still_allowed_and_also_names_an_upgrade(kind: str) -> None:
    limit = ent.QUANTITY_LIMITS[kind]["basics"]
    grace = ent.quantity_gate(
        kind, limit + GRACE_BAND, "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND
    )
    assert grace.state is ent.GateState.GRACE
    assert grace.upsell is not None  # forewarned before the hard block


# --- visibility contract: ceiling + reason are NEVER hidden, at every state --


@pytest.mark.parametrize("kind", DIMENSIONS)
@pytest.mark.parametrize("state_key", ["ok", "soft_warn", "grace", "block"])
def test_ceiling_and_reason_always_visible(kind: str, state_key: str) -> None:
    limit = ent.QUANTITY_LIMITS[kind]["basics"]
    current = _points(limit)[state_key]
    decision = ent.quantity_gate(
        kind, current, "basics", warn_ratio=WARN_RATIO, grace_band=GRACE_BAND
    )
    assert decision.visible is True
    assert decision.limit == limit
    assert decision.reason  # non-empty, always present
    assert str(limit) in decision.reason  # the ceiling itself is named in the reason


def test_ok_state_has_no_upsell_yet() -> None:
    # nothing to upgrade toward while comfortably under the limit
    decision = ent.quantity_gate("seats", 0, "basics")
    assert decision.state is ent.GateState.OK
    assert decision.upsell is None
    assert decision.visible is True


# --- defensive: unknown dimension / plan fail loud, never silently pass ------


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown quantity gate"):
        ent.quantity_gate("not_a_dimension", 1, "basics")


def test_unknown_plan_raises() -> None:
    with pytest.raises(ValueError, match="unknown plan"):
        ent.quantity_gate("headcount", 1, "enterprise")
