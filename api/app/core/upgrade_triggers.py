"""WS6.3 — upgrade-trigger events.

A pure DETECTOR: given a business event (``event_type`` + ``payload``) and the org's
CURRENT plan, decide whether the product should surface an upgrade/awareness pitch —
or nothing. Deterministic, no clock: any date a check needs travels in the payload,
never read from ``datetime.now()``.

Triggers are DATA (``_TRIGGERS`` below), not one-off per-event code — adding a new
trigger is a new table row, not a new branch scattered through callers.

Reuses ``app.core.entitlements`` for plan membership (``min_plan_for``) — never
duplicates the plan map here. Not wired into any router (§ ticket scope): the caller
(a future WS4.5/WS7 integration) is responsible for invoking :func:`detect` at the
actual product moment and rendering ``pitch_key`` via the UI's copy table.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.core import entitlements as ent
from app.core.money import Paise

#: PRODUCT-CONFIRMABLE (§0.6): AATO ₹5Cr is the figure named by WS6.3 itself (not
#: recalled from training) — it also matches the GST e-invoice manifest description
#: ("> ₹5Cr") already in the registry. Not a re-derivation of the statutory e-invoicing
#: threshold; a product trigger point that happens to track it.
AATO_5CR_PAISE: Paise = Paise.from_rupees(50_000_000)  # 5,00,00,000 = 5 crore rupees


@dataclass(frozen=True)
class UpgradeTrigger:
    """A single fired trigger: what to pitch, and why."""

    name: str  # stable id, e.g. "employee_11"
    event_type: str
    target: str  # human label of what's being pitched, e.g. "Bonus/Gratuity"
    target_feature: str | None  # a real entitlements.DOMAIN_FEATURES key, or None
    target_plan: str  # the plan that carries target_feature (or the direct pitch target)
    already_entitled: bool  # org's current plan already has target_feature
    pitch_key: str  # i18n/copy lookup key — UI owns the actual string
    why: str


@dataclass(frozen=True)
class _TriggerSpec:
    name: str
    event_type: str
    condition: Callable[[Mapping[str, Any]], bool]
    target: str
    target_feature: str | None
    default_plan: str  # used when target_feature is None (no single feature models it)
    pitch_key: str
    why: str


def _employee_11(payload: Mapping[str, Any]) -> bool:
    return int(payload["employee_count"]) >= 11


def _first_safe(payload: Mapping[str, Any]) -> bool:
    return int(payload["safe_count"]) == 1


def _aato_5cr(payload: Mapping[str, Any]) -> bool:
    return int(payload["aato_paise"]) >= int(AATO_5CR_PAISE)


def _second_gstin(payload: Mapping[str, Any]) -> bool:
    return int(payload["gstin_count"]) >= 2


def _board_meeting(payload: Mapping[str, Any]) -> bool:  # noqa: ARG001 - event type is the signal
    return True


#: The five named WS6.3 triggers. Order matters only for readability — each has a
#: distinct ``event_type`` so at most one can match a given call to :func:`detect`.
_TRIGGERS: tuple[_TriggerSpec, ...] = (
    _TriggerSpec(
        name="employee_11",
        event_type="employee_added",
        condition=_employee_11,
        target="Bonus/Gratuity",
        target_feature="gratuity",
        default_plan="basics",
        pitch_key="upgrade.employee_11.bonus_gratuity",
        why="headcount just crossed 10 — statutory bonus & gratuity provisioning "
        "becomes relevant; review the payroll compliance setup",
    ),
    _TriggerSpec(
        name="first_safe",
        event_type="safe_note_recorded",
        condition=_first_safe,
        target="Equity",
        target_feature="safe_notes",
        default_plan="startup",
        pitch_key="upgrade.first_safe.equity",
        why="first SAFE note recorded — the Equity module (cap table, dilution, "
        "conversion modelling) is the natural next step",
    ),
    _TriggerSpec(
        name="aato_5cr",
        event_type="aato_updated",
        condition=_aato_5cr,
        target="e-invoice add-on",
        target_feature="e_invoice",
        default_plan="startup",
        pitch_key="upgrade.aato_5cr.e_invoice",
        why="Annual Aggregate Turnover crossed ₹5Cr — e-Invoice IRN generation "
        "becomes operationally relevant",
    ),
    _TriggerSpec(
        name="second_gstin",
        event_type="gstin_registered",
        condition=_second_gstin,
        target="Growth",
        target_feature=None,  # multi-GSTIN (WS4.1 G6) is architectural, not a single key
        default_plan="growth",
        pitch_key="upgrade.second_gstin.growth",
        why="a second GSTIN registration means multi-GSTIN scoped ledgers/ITC/returns",
    ),
    _TriggerSpec(
        name="board_meeting",
        event_type="board_meeting_scheduled",
        condition=_board_meeting,
        target="secretarial",
        target_feature="secretarial",
        default_plan="growth",
        pitch_key="upgrade.board_meeting.secretarial",
        why="a board meeting is on the calendar — minutes/resolutions/AGM tracking "
        "(Secretarial compliance) keeps the record MCA-ready",
    ),
)


def detect(event_type: str, payload: Mapping[str, Any], plan: str) -> UpgradeTrigger | None:
    """Given a business event and the org's current plan, return the trigger to surface,
    or ``None`` if nothing about this event/payload/plan combination is a product moment.

    Pure and deterministic: same ``(event_type, payload, plan)`` -> same result, no clock,
    no I/O. An unrecognised ``event_type`` simply yields ``None`` (arbitrary product events
    are expected to not match any trigger — this is not an error).
    """
    if plan not in ent.PLAN_ORDER:
        raise ValueError(f"unknown plan {plan!r}; expected one of {ent.PLAN_ORDER}")

    for spec in _TRIGGERS:
        if spec.event_type != event_type:
            continue
        if not spec.condition(payload):
            continue

        target_plan = (
            ent.min_plan_for(spec.target_feature) if spec.target_feature else spec.default_plan
        )
        already = ent.is_entitled(plan, spec.target_feature) if spec.target_feature else False

        return UpgradeTrigger(
            name=spec.name,
            event_type=spec.event_type,
            target=spec.target,
            target_feature=spec.target_feature,
            target_plan=target_plan,
            already_entitled=already,
            pitch_key=spec.pitch_key,
            why=spec.why,
        )

    return None
