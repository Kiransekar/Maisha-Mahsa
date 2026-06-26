"""GST composition scheme + LUT exports — deferred features."""

from __future__ import annotations

import pytest

from app.core.money import Paise
from app.domains.gst.gst_calc import composition_tax, lut_export, lut_validity


def test_composition_rates() -> None:
    trader = composition_tax(Paise.from_rupees(1000000), category="trader")  # 1%
    assert trader["rate_pct"] == 1.0 and trader["tax"] == Paise.from_rupees(10000)
    rest = composition_tax(Paise.from_rupees(1000000), category="restaurant")  # 5%
    assert rest["tax"] == Paise.from_rupees(50000)
    svc = composition_tax(Paise.from_rupees(1000000), category="service")  # 6%
    assert svc["tax"] == Paise.from_rupees(60000)


def test_composition_unknown_category() -> None:
    with pytest.raises(ValueError):
        composition_tax(1000, category="bogus")


def test_lut_export_zero_rated() -> None:
    out = lut_export(Paise.from_rupees(500000))
    assert out["igst"] == 0 and out["zero_rated"] is True


def test_lut_validity_to_fy_end() -> None:
    assert lut_validity("2026-05-10") == "2027-03-31"  # FY 2026-27
    assert lut_validity("2026-02-10") == "2026-03-31"  # FY 2025-26
