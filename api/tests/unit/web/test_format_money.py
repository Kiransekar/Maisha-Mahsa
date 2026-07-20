"""The canonical Indian lakh/crore money renderer (§WS7.1). Every money surface routes
through app.web.format.inr / inr_rupees — so if grouping breaks, it breaks everywhere. Lock it."""

from __future__ import annotations

import pytest

from app.web.format import fmt_value, inr, inr_rupees


@pytest.mark.parametrize(
    "paise,expected",
    [
        (0, "₹0.00"),
        (100, "₹1.00"),
        (12345, "₹123.45"),
        (100000, "₹1,000.00"),
        (100000000, "₹10,00,000.00"),  # 10 lakh
        (123456700, "₹12,34,567.00"),  # lakh grouping, the spec example
        (1234567800, "₹1,23,45,678.00"),  # crore grouping
        (100000000000, "₹1,00,00,00,000.00"),  # 100 crore
        (-123456700, "-₹12,34,567.00"),  # negative keeps grouping, sign leads
        (-1, "-₹0.01"),
        (99, "₹0.99"),  # paise-only
    ],
)
def test_inr_indian_grouping(paise: int, expected: str) -> None:
    assert inr(paise) == expected


def test_inr_never_western_grouping() -> None:
    # Western would be ₹1,234,567.00 — the Indian renderer must not produce a 3-digit head group.
    assert inr(123456700) == "₹12,34,567.00"
    assert "," in inr(123456700)
    assert inr(123456700) != "₹1,234,567.00"


def test_inr_rupees_from_rupee_amount() -> None:
    assert inr_rupees("1234567") == "₹12,34,567.00"
    assert inr_rupees("150.50") == "₹150.50"
    assert inr_rupees(0) == "₹0.00"


def test_fmt_value_routes_money_through_canonical_renderer() -> None:
    # paise-keyed and known money keys → paise; _rupees keys → rupees; both Indian-grouped.
    assert fmt_value("tds_paise", 123456700) == "₹12,34,567.00"
    assert fmt_value("cash", 100000000) == "₹10,00,000.00"
    assert fmt_value("penalty_rupees", "1234567") == "₹12,34,567.00"
    # non-money passes through untouched
    assert fmt_value("count", 42) == "42"
