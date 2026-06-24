"""Dividend distribution (s.123) — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.equity.equity_calc import dividend_distribution


def test_dividend_within_profit_is_permitted() -> None:
    res = dividend_distribution(
        distributable_profit=Paise.from_rupees(1000000), declared=Paise.from_rupees(500000),
        shares=1000000,
    )
    assert res["permitted"] is True
    assert res["per_share"] == 50  # ₹5,00,000 / 10,00,000 shares = 50 paise
    assert res["remaining_profit"] == Paise.from_rupees(500000)


def test_dividend_exceeding_profit_blocked() -> None:
    res = dividend_distribution(
        distributable_profit=Paise.from_rupees(1000000), declared=Paise.from_rupees(2000000),
        shares=1000000,
    )
    assert res["permitted"] is False  # cannot declare out of capital (s.123)
    assert res["declared"] == 0
    assert res["remaining_profit"] == Paise.from_rupees(1000000)
