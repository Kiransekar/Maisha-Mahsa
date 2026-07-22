"""Unit-level cover for :mod:`app.core.entitlement_deps` — the pure decision layer only.

THE HTTP BEHAVIOUR IS NOT PROVEN HERE. It is proven in
``tests/integration/test_entitlement_routes.py``, which drives the real app with real signed
tokens over real HTTP. This file deliberately does NOT build a fake auth middleware that sets
an invented ``request.state`` contract — that is exactly the hollow test this round exists to
delete. What is left is what HTTP tests cover expensively: every grace feature, every quantity
state, and the definition-time key check.

Each dependency here is invoked with a real :class:`SessionContext` — the same object
``get_session_context`` builds from the verified token — so no request plumbing is faked.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import entitlements as ent
from app.core.entitlement_deps import (
    DEFAULT_PLAN,
    SessionContext,
    entitlement_payload,
    require_feature,
    require_quantity,
)

BASICS = SessionContext(org_id="org-1", org_plan="basics")


# --- definition-time key validation (the cardinal defect) --------------------------------


@pytest.mark.parametrize("key", ["totally_made_up", "gstr3B", "", "cap_tabel"])
def test_unregistered_key_cannot_become_a_paywall(key: str) -> None:
    with pytest.raises(ValueError, match="FEATURE_REGISTRY"):
        require_feature(key)


def test_every_registry_key_is_accepted() -> None:
    for key in ent.FEATURE_REGISTRY:
        assert require_feature(key) is not None


def test_unknown_quantity_kind_rejected_at_definition_time() -> None:
    with pytest.raises(ValueError, match="unknown quantity gate"):
        require_quantity("nope", current=lambda _ctx: 0)


# --- require_feature decisions ----------------------------------------------------------


def test_entitled_feature_passes() -> None:
    decision = require_feature("payroll_run")(BASICS)  # basics feature
    assert decision.allowed and not decision.grace


def test_locked_feature_402s_visible_with_reason_and_upsell() -> None:
    with pytest.raises(HTTPException) as exc:
        require_feature("secretarial")(BASICS)  # growth-only
    assert exc.value.status_code == 402  # never 403/404 — locked stays VISIBLE (WS6.2)
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["upsell"] == "growth" and "Growth" in detail["reason"]


def test_every_statutory_grace_feature_passes_on_the_lowest_plan() -> None:
    """The load-bearing rule, over the whole set: no legal filing is ever blocked."""
    for feature in sorted(ent.STATUTORY_GRACE_FEATURES):
        decision = require_feature(feature)(SessionContext("org-1", DEFAULT_PLAN))
        assert decision.allowed, f"statutory filing {feature} was blocked"
        payload = entitlement_payload(decision)
        if not ent.is_entitled(DEFAULT_PLAN, feature):
            # not on the plan -> allowed anyway, and the upsell is carried for the route
            assert payload["grace"] is True and payload["upsell"] is not None


# --- require_quantity states ------------------------------------------------------------


@pytest.mark.parametrize(
    ("headcount", "state"),
    [(1, "ok"), (9, "soft_warn"), (10, "soft_warn"), (12, "grace")],
)
def test_quantity_gate_passes_below_block_with_the_ceiling_visible(
    headcount: int, state: str
) -> None:
    decision = require_quantity("headcount", current=lambda _ctx: headcount)(BASICS)
    assert decision.state.value == state
    assert decision.limit == 10 and decision.visible


def test_quantity_gate_blocks_beyond_grace_with_ceiling_and_count() -> None:
    with pytest.raises(HTTPException) as exc:
        require_quantity("headcount", current=lambda _ctx: 13)(BASICS)
    assert exc.value.status_code == 403
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["current"] == 13 and detail["limit"] == 10 and detail["upsell"] == "startup"


def test_quantity_count_comes_from_the_session_context_not_the_caller() -> None:
    seen: list[SessionContext] = []
    require_quantity("seats", current=lambda ctx: (seen.append(ctx), 1)[1])(BASICS)
    assert seen == [BASICS]
