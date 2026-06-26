"""Mileage / per-diem travel — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.expense.expense_calc import mileage_claim, per_diem


def test_mileage_claim() -> None:
    # 120 km at ₹12/km = ₹1,440
    assert mileage_claim(120, rate_per_km=Paise.from_rupees(12)) == Paise.from_rupees(1440)


def test_per_diem() -> None:
    # 3 days at ₹2,000/day = ₹6,000
    assert per_diem(3, rate_per_day=Paise.from_rupees(2000)) == Paise.from_rupees(6000)
