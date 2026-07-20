"""WS6.1 — Tier-entitlement architecture.

Feature registry (every domain-manifest feature + a small platform baseline) → a
cumulative plan map (Basics ⊂ Startup ⊂ Growth) stored as DATA in ``plans.yaml`` →
enforcement helpers: :func:`is_entitled`, the middleware-shaped :func:`guard`, the
statutory-grace override, and a :func:`quantity_gate` stub.

Design invariants
-----------------
* §0.8 SECURITY: the org's plan comes from the verified SESSION context
  (:func:`plan_from_context`), NEVER from a request body.
* §0.6: the split COUNTS (71 / +34 / +11 = 116) are fixed by WS6.1; the exact
  feature→plan assignment in ``plans.yaml`` is a PRODUCT-CONFIRMABLE default.
* Statutory-grace: a legal filing is NEVER blocked mid-flow, even on a lower plan —
  it is allowed, logged, and an upsell is surfaced *after* the flow.
* Locked features are always VISIBLE-with-reason, never hidden.

Not wired into any router here — live user/session/org context arrives in WS4.3/WS5.2.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domains.compliance.manifest import MANIFEST as _compliance
from app.domains.equity.manifest import MANIFEST as _equity
from app.domains.expense.manifest import MANIFEST as _expense
from app.domains.forecast.manifest import MANIFEST as _forecast
from app.domains.gst.manifest import MANIFEST as _gst
from app.domains.ledger.manifest import MANIFEST as _ledger
from app.domains.payables.manifest import MANIFEST as _payables
from app.domains.payroll.manifest import MANIFEST as _payroll
from app.domains.revenue.manifest import MANIFEST as _revenue
from app.domains.tax.manifest import MANIFEST as _tax
from app.domains.treasury.manifest import MANIFEST as _treasury
from app.domains.vault.manifest import MANIFEST as _vault

_log = logging.getLogger("maisha.entitlements")

# --- feature registry --------------------------------------------------------

_MANIFESTS = (
    _treasury, _revenue, _payables, _payroll, _gst, _tax,
    _ledger, _forecast, _equity, _compliance, _expense, _vault,
)

#: Every entitlement-controlled DOMAIN feature key (the 116 that the plan map splits).
DOMAIN_FEATURES: frozenset[str] = frozenset(
    f.key for m in _MANIFESTS for f in m.features
)

#: Platform baseline — always entitled on every plan, so it is NOT part of the
#: 71/34/11 split. These are the things every tenant needs regardless of tier.
PLATFORM_KEYS: frozenset[str] = frozenset(
    {
        "platform.dashboard",   # the Today/home surface
        "platform.audit_log",   # hash-chained audit trail (non-disablable)
        "platform.notifications",
        "platform.support",
    }
)

#: The full entitlement key space.
FEATURE_REGISTRY: frozenset[str] = DOMAIN_FEATURES | PLATFORM_KEYS

# --- plan map (data) ---------------------------------------------------------

PLAN_ORDER: tuple[str, ...] = ("basics", "startup", "growth")
_PLANS_PATH = Path(__file__).with_name("plans.yaml")


def _load_plan_layers() -> dict[str, list[str]]:
    data = yaml.safe_load(_PLANS_PATH.read_text(encoding="utf-8"))
    return {
        "basics": list(data["basics"]),
        "startup_adds": list(data["startup_adds"]),
        "growth_adds": list(data["growth_adds"]),
    }


_LAYERS = _load_plan_layers()

#: Cumulative feature set per plan: Basics ⊂ Startup ⊂ Growth.
_PLAN_FEATURES: dict[str, frozenset[str]] = {
    "basics": frozenset(_LAYERS["basics"]),
    "startup": frozenset(_LAYERS["basics"]) | frozenset(_LAYERS["startup_adds"]),
    "growth": (
        frozenset(_LAYERS["basics"])
        | frozenset(_LAYERS["startup_adds"])
        | frozenset(_LAYERS["growth_adds"])
    ),
}

#: Statutory FILINGS that must never be blocked mid-flow (grace + log + upsell-after),
#: even for a tenant on a plan that does not include the feature. Every key is a real
#: filing/return/statutory-contribution feature drawn from the registry.
STATUTORY_GRACE_FEATURES: frozenset[str] = frozenset(
    {
        # GST returns
        "gstr1", "gstr3b", "gstr9", "e_invoice",
        # income-tax / TDS filings
        "advance_tax", "tds_returns", "itr", "form_26as",
        # payroll statutory contributions & filings
        "pf", "esi", "pt", "lwf", "ecr", "form16",
        # MCA / compliance filings
        "mca_filings", "mark_filed",
    }
)


def validate_registry() -> None:
    """Fail loud if ``plans.yaml`` does not partition the 116 domain features exactly.

    Runs at import so a bad edit to the data file cannot silently ship a wrong split.
    """
    layers = [_LAYERS["basics"], _LAYERS["startup_adds"], _LAYERS["growth_adds"]]
    flat = [k for layer in layers for k in layer]

    dupes = [k for k in flat if flat.count(k) > 1]
    if dupes:
        raise ValueError(f"plans.yaml: feature in more than one plan: {sorted(set(dupes))}")

    assigned = set(flat)
    strays = assigned - DOMAIN_FEATURES
    if strays:
        raise ValueError(f"plans.yaml: feature key(s) not in any manifest: {sorted(strays)}")

    missing = DOMAIN_FEATURES - assigned
    if missing:
        raise ValueError(f"plans.yaml: feature(s) not assigned to any plan: {sorted(missing)}")

    counts = (len(_LAYERS["basics"]), len(_LAYERS["startup_adds"]), len(_LAYERS["growth_adds"]))
    if counts != (71, 34, 11):
        raise ValueError(f"plans.yaml: split counts {counts} != agreed (71, 34, 11)")

    if not STATUTORY_GRACE_FEATURES <= DOMAIN_FEATURES:
        raise ValueError("STATUTORY_GRACE_FEATURES contains keys outside the registry")


def plan_counts() -> dict[str, int]:
    """Feature COUNTS per layer: ``{'basics': 71, 'startup_adds': 34, 'growth_adds': 11}``."""
    return {
        "basics": len(_LAYERS["basics"]),
        "startup_adds": len(_LAYERS["startup_adds"]),
        "growth_adds": len(_LAYERS["growth_adds"]),
    }


# --- enforcement -------------------------------------------------------------


def is_entitled(plan: str, feature: str) -> bool:
    """True iff ``plan`` includes ``feature``. Platform baseline is always entitled.

    Unknown ``feature`` → False (fail closed for entitlement, but see :func:`guard`
    which still keeps the feature VISIBLE-with-reason). Unknown ``plan`` → ValueError.
    """
    if plan not in _PLAN_FEATURES:
        raise ValueError(f"unknown plan {plan!r}; expected one of {PLAN_ORDER}")
    if feature in PLATFORM_KEYS:
        return True
    return feature in _PLAN_FEATURES[plan]


def min_plan_for(feature: str) -> str:
    """Lowest plan that unlocks ``feature`` (the upsell target). Platform → 'basics'."""
    if feature in PLATFORM_KEYS:
        return "basics"
    for plan in PLAN_ORDER:
        if feature in _PLAN_FEATURES[plan]:
            return plan
    return "growth"  # unknown key: nothing unlocks it; point at the top plan


@dataclass(frozen=True)
class GuardDecision:
    """Middleware-shaped verdict. ``visible`` is ALWAYS True — locked features are shown
    with a reason and an upsell, never hidden (WS6.1)."""

    feature: str
    plan: str
    allowed: bool
    grace: bool
    visible: bool
    reason: str
    upsell: str | None  # plan to upgrade to, or None when already entitled


def guard(plan: str, feature: str) -> GuardDecision:
    """The enforcement point a route middleware would call (once auth lands in WS4.3).

    * entitled                     → allowed, no upsell.
    * statutory filing, not on plan → GRACE: allowed + logged + upsell-after (never block).
    * anything else, not on plan    → denied, but VISIBLE-with-reason + upsell.
    """
    if is_entitled(plan, feature):
        return GuardDecision(
            feature=feature, plan=plan, allowed=True, grace=False,
            visible=True, reason="entitled", upsell=None,
        )

    need = min_plan_for(feature)

    if feature in STATUTORY_GRACE_FEATURES:
        # §0.8: keys only, no PII in the log line.
        _log.info(
            "entitlement.statutory_grace feature=%s plan=%s upsell=%s", feature, plan, need
        )
        return GuardDecision(
            feature=feature, plan=plan, allowed=True, grace=True, visible=True,
            reason="statutory-grace: a legal filing is never blocked mid-flow; upsell after",
            upsell=need,
        )

    return GuardDecision(
        feature=feature, plan=plan, allowed=False, grace=False, visible=True,
        reason=f"locked: available on the {need.title()} plan",
        upsell=need,
    )


# --- quantity gates (stub — full engine is WS6.2) ----------------------------


class GateState(enum.StrEnum):
    OK = "ok"
    SOFT_WARN = "soft_warn"  # approaching the limit
    GRACE = "grace"          # over the limit, temporarily allowed
    BLOCK = "block"          # over the grace band → upgrade required


#: Per-plan quantity ceilings. PRODUCT-CONFIRMABLE defaults; headcount tiers 10/50/200
#: are the WS6.2 fair-use figures.
QUANTITY_LIMITS: dict[str, dict[str, int]] = {
    "headcount": {"basics": 10, "startup": 50, "growth": 200},
    "seats": {"basics": 3, "startup": 10, "growth": 25},
    "entities": {"basics": 1, "startup": 3, "growth": 10},
}


@dataclass(frozen=True)
class GateDecision:
    kind: str
    plan: str
    current: int
    limit: int
    state: GateState
    visible: bool  # always True — the ceiling is shown with a reason
    reason: str
    upsell: str | None


def quantity_gate(
    kind: str, current: int, plan: str, *, warn_ratio: float = 0.8, grace_band: int = 2
) -> GateDecision:
    """Soft-warn → grace → block for a countable resource (WS6.2 stub).

    ``warn_ratio`` of the limit → SOFT_WARN; over the limit but within ``grace_band`` →
    GRACE (still allowed); beyond that → BLOCK-with-upgrade. The ceiling is always visible.
    """
    if kind not in QUANTITY_LIMITS:
        raise ValueError(f"unknown quantity gate {kind!r}; expected {sorted(QUANTITY_LIMITS)}")
    if plan not in _PLAN_FEATURES:
        raise ValueError(f"unknown plan {plan!r}; expected one of {PLAN_ORDER}")

    limit = QUANTITY_LIMITS[kind][plan]
    # upgrade target: the lowest higher plan whose limit clears `current`, if any.
    upsell = next(
        (p for p in PLAN_ORDER[PLAN_ORDER.index(plan) + 1:] if QUANTITY_LIMITS[kind][p] >= current),
        None,
    )

    if current <= warn_ratio * limit:
        state, reason = GateState.OK, f"{current}/{limit} {kind}"
    elif current <= limit:
        state, reason = GateState.SOFT_WARN, f"approaching {kind} limit ({current}/{limit})"
    elif current <= limit + grace_band:
        state, reason = GateState.GRACE, f"over {kind} limit ({current}/{limit}); grace active"
    else:
        state, reason = GateState.BLOCK, f"{kind} limit exceeded ({current}/{limit}); upgrade"

    return GateDecision(
        kind=kind, plan=plan, current=current, limit=limit, state=state,
        visible=True, reason=reason,
        upsell=upsell if state in (GateState.GRACE, GateState.BLOCK) else None,
    )


# --- session-context plan source (§0.8) --------------------------------------


def plan_from_context(ctx: Any) -> str:
    """Resolve the org plan from the VERIFIED session context ONLY (§0.8).

    ``ctx`` is whatever the auth layer (WS4.3) attaches to the request — an object with
    an ``org_plan`` attribute or a mapping with an ``"org_plan"`` key. The plan must NEVER
    be read from a request body/query/header supplied by the caller.
    """
    plan = getattr(ctx, "org_plan", None)
    if plan is None and isinstance(ctx, dict):
        plan = ctx.get("org_plan")
    if plan not in _PLAN_FEATURES:
        raise ValueError("org plan missing/invalid in session context; refusing to default")
    return str(plan)


validate_registry()  # fail loud at import if the data file drifts from the agreed split
