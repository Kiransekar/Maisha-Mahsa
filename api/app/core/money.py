"""Exact money. The Python mirror of `dif/src/money.rs`.

Internally money is **integer paise** (1 INR = 100 paise). Floats are never used for
money math. Conversions go through `Decimal` with explicit rounding so results are exact
and reproducible — a wrong paise is a compliance defect, not a rounding nicety.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_HUNDRED = Decimal(100)


class Paise(int):
    """An amount in integer paise. ``Paise.from_rupees("150.50") == Paise(15050)``."""

    __slots__ = ()

    @classmethod
    def from_rupees(cls, rupees: str | int | float | Decimal) -> Paise:
        """Construct from a rupee amount. ``float`` is accepted but routed through
        ``Decimal(str(...))`` so e.g. ``0.1`` does not leak binary error."""
        d = Decimal(str(rupees)) * _HUNDRED
        return cls(int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))

    @classmethod
    def from_paise(cls, paise: int) -> Paise:
        return cls(int(paise))

    @property
    def rupees(self) -> Decimal:
        """Exact rupee value as ``Decimal`` — for display, never for further money math."""
        return Decimal(int(self)) / _HUNDRED

    def format_inr(self) -> str:
        """Indian-grouped rupee string, e.g. ``₹12,34,567.00`` (UI polish requirement)."""
        sign = "-" if self < 0 else ""
        whole, frac = divmod(abs(int(self)), 100)
        s = str(whole)
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            # group the head in pairs (Indian system: ..,xx,xx,xxx)
            parts: list[str] = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            s = ",".join(parts) + "," + tail
        return f"{sign}₹{s}.{frac:02d}"


ZERO = Paise(0)
