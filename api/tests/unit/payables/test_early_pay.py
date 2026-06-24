"""Early-payment discount capture — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.payables.payables_calc import early_payment_discount


def test_discount_captured_within_window() -> None:
    # "2/10 net 30": 2% off a ₹1,00,000 invoice if paid within 10 days
    res = early_payment_discount(
        Paise.from_rupees(100000), discount_pct=2, discount_days=10, paid_in_days=8
    )
    assert res["eligible"] is True
    assert res["discount"] == Paise.from_rupees(2000)
    assert res["net_payable"] == Paise.from_rupees(98000)


def test_no_discount_after_window() -> None:
    res = early_payment_discount(
        Paise.from_rupees(100000), discount_pct=2, discount_days=10, paid_in_days=15
    )
    assert res["eligible"] is False
    assert res["discount"] == 0
    assert res["net_payable"] == Paise.from_rupees(100000)
