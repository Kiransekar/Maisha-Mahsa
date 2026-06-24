"""Reverse-charge mechanism — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.gst.gst_calc import rcm_liability


def test_rcm_tax_and_itc() -> None:
    res = rcm_liability([{"taxable": Paise.from_rupees(100000), "rate": 18}])
    assert res["taxable_value"] == Paise.from_rupees(100000)
    assert res["rcm_tax_payable"] == Paise.from_rupees(18000)
    assert res["itc_available"] == Paise.from_rupees(18000)  # recipient pays, then claims ITC


def test_rcm_multiple_supplies() -> None:
    res = rcm_liability([
        {"taxable": Paise.from_rupees(100000), "rate": 18},
        {"taxable": Paise.from_rupees(50000), "rate": 5},
    ])
    assert res["rcm_tax_payable"] == Paise.from_rupees(18000) + Paise.from_rupees(2500)
