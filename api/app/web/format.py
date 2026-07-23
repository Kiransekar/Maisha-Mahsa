"""View-layer formatting helpers. Turn raw snapshot/fact values into display strings — money
in Indian-grouped rupees, everything else humanized. Pure; no IO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.money import Paise

# Money facts that are integer paise but don't carry a ``_paise`` suffix.
_MONEY_PAISE_KEYS = {"cash", "ap_total", "monthly_burn", "monthly_revenue", "net_burn"}


def is_money(key: str) -> bool:
    return key.endswith("_paise") or key in _MONEY_PAISE_KEYS


def inr(paise: int) -> str:
    """THE money renderer (§WS7.1). Every money surface — templates (via the ``rupees`` Jinja
    filter), PDFs, API display — routes rupee formatting through here so grouping is always the
    Indian lakh/crore system (``₹12,34,567.00``), never Western thousands. Delegates to the ported
    ``Paise.format_inr`` (the Python mirror of ``dif/src/money.rs``). Never hand-assemble ``₹`` +
    a value anywhere else; ``scripts/check_money_format.sh`` fails the build if you do."""
    return Paise(int(paise)).format_inr()


def inr_rupees(rupees: str | int | float) -> str:
    """The same canonical renderer, from a rupee amount rather than integer paise."""
    return Paise.from_rupees(rupees).format_inr()


def humanize(key: str) -> str:
    base = key
    for suffix in ("_paise", "_rupees"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base.replace("_", " ").strip().capitalize()


def fmt_value(key: str, value: Any) -> str:
    """Format a single fact for display. Money keys render as ₹ Indian-grouped; ``_rupees``
    keys are rupee amounts, ``_paise``/known-money keys are paise."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if key.endswith("_rupees"):
        try:
            return inr_rupees(value)
        except (ValueError, TypeError, ArithmeticError):
            return str(value)
    if is_money(key):
        try:
            return inr(value)
        except (ValueError, TypeError):
            return str(value)
    return str(value)


@dataclass(frozen=True)
class FactRow:
    label: str
    value: str


def fact_rows(facts: dict[str, Any]) -> list[FactRow]:
    """Display rows for a flattened fact map, sorted by label, excluding the ``as_of`` stamp."""
    return [FactRow(humanize(k), fmt_value(k, v)) for k, v in sorted(facts.items()) if k != "as_of"]
