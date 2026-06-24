"""Deterministic tools the drafting layer relies on instead of doing its own arithmetic
(SWE-agent ACI discipline: the model selects and narrates, the tools compute). Each tool is a
thin wrapper over the audited domain calc functions and produces canonical decimal **strings**
(paise for money) so its outputs drop straight into an ``ActionClaim``.

The generator calls :func:`enrich` to flatten a Mahsa snapshot into a flat ``facts`` map and
then apply every tool whose inputs are present — so every number the model sees (including
derived ones like runway) was computed deterministically, never by the LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domains.gst.gst_calc import late_fee_3b


class ToolError(ValueError):
    """A tool was given inputs it can't use (e.g. non-numeric). Surfaced to the model as a
    precise message so it can correct course rather than guess."""


def _as_int(facts: dict[str, Any], key: str) -> int:
    try:
        return int(facts[key])
    except (KeyError, TypeError, ValueError) as exc:
        got = facts.get(key)
        raise ToolError(f"tool input {key!r} is missing or non-integer: {got!r}") from exc


def _treasury_runway(facts: dict[str, Any]) -> dict[str, str]:
    cash = _as_int(facts, "cash")
    net_burn = max(0, _as_int(facts, "monthly_burn") - _as_int(facts, "monthly_revenue"))
    if net_burn == 0:
        return {"net_burn_paise": "0"}  # cash-flow positive: runway is not burn-limited
    return {"net_burn_paise": str(net_burn), "runway_months": str(round(cash / net_burn, 2))}


def _gst_late_fee(facts: dict[str, Any]) -> dict[str, str]:
    return {"gstr3b_late_fee_paise": str(late_fee_3b(_as_int(facts, "gstr3b_days_late")))}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    inputs: tuple[str, ...]
    fn: Callable[[dict[str, Any]], dict[str, str]]

    def applies_to(self, facts: dict[str, Any]) -> bool:
        return all(k in facts for k in self.inputs)


REGISTRY: tuple[Tool, ...] = (
    Tool(
        name="treasury_runway",
        description="Months of runway = cash / (monthly burn − monthly revenue).",
        inputs=("cash", "monthly_burn", "monthly_revenue"),
        fn=_treasury_runway,
    ),
    Tool(
        name="gst_late_fee_3b",
        description="GSTR-3B late fee (₹50/day, capped) from days late.",
        inputs=("gstr3b_days_late",),
        fn=_gst_late_fee,
    ),
)


def flatten(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Mahsa snapshot (top-level fields + the ``metrics`` sub-dict) into one map.
    Non-scalar values are dropped — facts are numbers and short strings the model may quote."""
    out: dict[str, Any] = {}
    for k, v in snapshot.items():
        if k == "metrics" and isinstance(v, dict):
            continue
        if isinstance(v, (int, float, str)):
            out[k] = v
    metrics = snapshot.get("metrics")
    if isinstance(metrics, dict):
        for k, v in metrics.items():
            if isinstance(v, (int, float, str)):
                out[k] = v
    return out


def enrich(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Flatten then apply every applicable tool, merging deterministic derived values in."""
    facts = flatten(snapshot)
    for tool in REGISTRY:
        if tool.applies_to(facts):
            facts.update(tool.fn(facts))
    return facts
