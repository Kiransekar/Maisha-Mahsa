"""Auto-sweep / FD-laddering suggestion — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.treasury.service import sweep_suggestion


def test_idle_cash_is_sweepable() -> None:
    # ₹1Cr cash, ₹10L/mo net burn, 6-month buffer (₹60L) -> ₹40L sweepable
    res = sweep_suggestion(Paise.from_rupees(10000000), Paise.from_rupees(1000000), buffer_months=6)
    assert res["buffer_required"] == Paise.from_rupees(6000000)
    assert res["sweepable"] == Paise.from_rupees(4000000)
    assert res["recommend_sweep"] is True


def test_no_sweep_when_below_buffer() -> None:
    res = sweep_suggestion(Paise.from_rupees(3000000), Paise.from_rupees(1000000), buffer_months=6)
    assert res["sweepable"] == 0 and res["recommend_sweep"] is False
