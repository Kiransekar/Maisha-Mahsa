"""HSN master / rate lookup — deferred feature."""

from __future__ import annotations

from app.domains.gst.gst_calc import hsn_rate

_MASTER = {"9983": 18.0, "1006": 5.0}


def test_lookup_found() -> None:
    res = hsn_rate("9983", _MASTER)
    assert res["found"] is True and res["rate"] == 18.0 and res["well_formed"] is True


def test_lookup_missing_but_well_formed() -> None:
    res = hsn_rate("8471", _MASTER)
    assert res["found"] is False and res["rate"] is None and res["well_formed"] is True


def test_malformed_code() -> None:
    res = hsn_rate("99", _MASTER)
    assert res["well_formed"] is False
