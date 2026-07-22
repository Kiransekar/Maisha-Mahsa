"""WS6.1-wiring — the FastAPI dependency layer for :mod:`app.core.entitlements`.

``entitlements.py`` has the registry, plan map, ``is_entitled``/``guard`` and the
statutory-grace override. This module is the wiring: two dependency factories,
``require_feature`` and ``require_quantity``, that a route adds to its ``Depends(...)``
list, plus the resolution of WHICH PLAN the caller is on.

WHERE THE PLAN COMES FROM (§0.8). Two verified facts, no third source:
  * ``org_id``  — from the :class:`~app.core.principal.Principal` the auth middleware
    verified and stashed on ``request.state`` (``betterauth.get_principal``). No
    principal -> 401, always.
  * ``org_plan`` — from a CLAIM ON THE SAME SIGNATURE-VERIFIED Better Auth JWT. Never a
    body, query param, or header. The claim name is ``MAISHA_BETTER_AUTH_PLAN_CLAIM``,
    defaulting to ``plan``; the owner adds it to the Better Auth JWT payload alongside
    ``activeOrganizationId`` (the org's tier lives in ``orgs.plan``, see
    ``infra/db/multitenant/001_tenancy.sql``).

    A token with NO plan claim, or an unrecognised value, resolves to ``basics`` — which
    is not an invention: it is the column default (``plan text NOT NULL DEFAULT 'basics'``)
    in that same file, and it is the LEAST-privileged tier, so an unconfigured deployment
    fails towards fewer features, never more. It is also loud: the 402 body names
    ``plan: "basics"``, so a wrongly-locked tenant is diagnosable from the response alone.
    Statutory filings are unaffected either way — see the grace override below.

WS6.2 contract (never relax): a locked feature is VISIBLE with its reason and upgrade
target, never a bare 404. A statutory filing is NEVER blocked mid-flow — ``guard()``
allows it, logs it, and returns the upsell for the route to surface AFTER the action.

CARDINAL (this round): ``require_feature(key)`` validates ``key`` against
``FEATURE_REGISTRY`` AT DEFINITION TIME. A typo (``gstr3B``) or an invented key used to
return a plausible "locked, upgrade to Growth" 402 — a paywall no plan could ever
unlock. It is now an ImportError-time crash instead.
"""

from __future__ import annotations

import difflib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request

from app.core import betterauth
from app.core.entitlements import (
    FEATURE_REGISTRY,
    QUANTITY_LIMITS,
    GateDecision,
    GateState,
    GuardDecision,
    guard,
    plan_from_context,
    quantity_gate,
)

_log = logging.getLogger("maisha.entitlements")

#: Env var naming the JWT claim that carries the org's tier. See module docstring.
PLAN_CLAIM_ENV = "MAISHA_BETTER_AUTH_PLAN_CLAIM"
DEFAULT_PLAN_CLAIM = "plan"

#: ``orgs.plan text NOT NULL DEFAULT 'basics'`` — infra/db/multitenant/001_tenancy.sql.
#: Least-privileged tier; used when the token carries no/an unknown plan claim.
DEFAULT_PLAN = "basics"


@dataclass(frozen=True)
class SessionContext:
    """The verified session facts a dependency is allowed to read. Nothing else."""

    org_id: str
    org_plan: str


def _plan_claim_name() -> str:
    return os.environ.get(PLAN_CLAIM_ENV, "").strip() or DEFAULT_PLAN_CLAIM


def _verified_plan(request: Request) -> str:
    """Read the org tier off the SIGNATURE-VERIFIED bearer token (§0.8)."""
    token = betterauth.bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="no bearer token: cannot resolve plan")
    try:
        # ponytail: re-verifies the signature the middleware already checked (one Ed25519
        # verify per gated request) because the middleware stashes the Principal, not the
        # claims. Upgrade path when it shows up in a profile: stash the claims on
        # request.state in app.main._authenticate and read them here.
        claims = betterauth.decode_claims(
            token,
            jwks_url=betterauth.better_auth_jwks_url(),
            issuer=betterauth.better_auth_issuer(),
            audience=betterauth.better_auth_audience(),
        )
    except betterauth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    try:
        return plan_from_context({"org_plan": claims.get(_plan_claim_name())})
    except ValueError:
        # §0.8: keys only, no PII, and never the token.
        _log.warning(
            "entitlement.plan_claim_unusable claim=%s -> %s", _plan_claim_name(), DEFAULT_PLAN
        )
        return DEFAULT_PLAN


def get_session_context(request: Request) -> SessionContext:
    """Resolve the session context from the VERIFIED token only (§0.8).

    ``org_id`` comes from the Principal the auth middleware verified;
    :func:`app.core.betterauth.get_principal` raises 401 when there isn't one (an
    unauthenticated request, or a legacy dev-cookie session, which carries no identity).
    """
    principal = betterauth.get_principal(request)
    return SessionContext(org_id=principal.org_id, org_plan=_verified_plan(request))


def _feature_payload(decision: GuardDecision) -> dict[str, Any]:
    return {
        "error": "feature_locked",
        "feature": decision.feature,
        "plan": decision.plan,
        "reason": decision.reason,
        "upsell": decision.upsell,
    }


def entitlement_payload(decision: GuardDecision) -> dict[str, Any]:
    """What a route puts in its 2xx body so a GRACE upsell is recorded after the fact."""
    return {
        "feature": decision.feature,
        "plan": decision.plan,
        "grace": decision.grace,
        "reason": decision.reason,
        "upsell": decision.upsell,
    }


def require_feature(key: str) -> Callable[..., GuardDecision]:
    """Dependency: gate a route behind entitlement ``key`` on the session's plan.

    ``key`` MUST be in :data:`app.core.entitlements.FEATURE_REGISTRY`. It is checked HERE,
    at dependency-definition time — i.e. at router import, so a typo is a startup crash,
    not a convincing 402 for a feature that does not exist.

    * entitled                -> passes, returns the :class:`GuardDecision`.
    * statutory-grace feature not on the plan -> ALSO passes (``guard`` logs it and marks
      ``grace=True``) — a legal filing is never blocked mid-flow. The route surfaces
      ``decision.upsell`` AFTER the action via :func:`entitlement_payload`.
    * anything else not on the plan -> 402 with reason + upgrade target in the body
      (never a bare 403/404 — the feature stays visible-with-reason, WS6.2).
    """
    if key not in FEATURE_REGISTRY:
        hint = difflib.get_close_matches(key, FEATURE_REGISTRY, n=3)
        raise ValueError(
            f"unknown entitlement key {key!r}: not in FEATURE_REGISTRY"
            + (f"; did you mean {hint}?" if hint else "")
        )

    def _dep(ctx: SessionContext = Depends(get_session_context)) -> GuardDecision:
        decision = guard(ctx.org_plan, key)
        if not decision.allowed:
            raise HTTPException(status_code=402, detail=_feature_payload(decision))
        return decision

    return _dep


def _quantity_payload(decision: GateDecision) -> dict[str, Any]:
    return {
        "error": "quantity_limit",
        "kind": decision.kind,
        "plan": decision.plan,
        "current": decision.current,
        "limit": decision.limit,
        "state": decision.state.value,
        "reason": decision.reason,
        "upsell": decision.upsell,
    }


def require_quantity(
    kind: str, current: Callable[[SessionContext], int]
) -> Callable[..., GateDecision]:
    """Dependency: quantity gate (headcount/seats/entities, WS6.2).

    ``kind`` is validated at definition time for the same reason ``require_feature``'s key
    is. ``current`` computes the live count from the session context (e.g. a headcount
    query scoped to ``ctx.org_id``) — never caller-supplied. Only ``BLOCK`` stops the
    request (403, ceiling + current count in the body); OK / SOFT_WARN / GRACE pass
    through carrying the same ceiling for the route to surface.
    """
    if kind not in QUANTITY_LIMITS:
        raise ValueError(f"unknown quantity gate {kind!r}; expected {sorted(QUANTITY_LIMITS)}")

    def _dep(ctx: SessionContext = Depends(get_session_context)) -> GateDecision:
        decision = quantity_gate(kind, current(ctx), ctx.org_plan)
        if decision.state is GateState.BLOCK:
            raise HTTPException(status_code=403, detail=_quantity_payload(decision))
        return decision

    return _dep


if __name__ == "__main__":  # ponytail: one runnable check; the real proof is over HTTP
    # (tests/integration/test_entitlement_routes.py drives the real app with real tokens).
    ctx = SessionContext(org_id="org1", org_plan="basics")

    assert require_feature("cash_position")(ctx).allowed  # Basics feature -> passes

    try:
        require_feature("totally_made_up")
    except ValueError as e:
        assert "FEATURE_REGISTRY" in str(e)
    else:
        raise AssertionError("an unregistered key must never become a plausible 402")

    try:
        require_feature("gstr3B")  # typo of gstr3b
    except ValueError as e:
        assert "gstr3b" in str(e)
    else:
        raise AssertionError("a typo'd key must never become a plausible 402")

    try:
        require_feature("secretarial")(ctx)  # Growth-only, ctx is basics
    except HTTPException as e:
        assert e.status_code == 402 and e.detail["upsell"] == "growth"  # type: ignore[index]
    else:
        raise AssertionError("locked feature must 402, never silently pass")

    grace = require_feature("itr")(ctx)  # statutory filing, not on basics -> still passes
    assert grace.allowed and grace.grace and entitlement_payload(grace)["upsell"] == "startup"

    print("entitlement_deps self-check ok")
