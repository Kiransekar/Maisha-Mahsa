"""WS1.D1 — 194Q / 194T / TCS s.394 / 206AA-206AB overlay. Asserts the spec-cited numbers
(MMX-1.0 §WS1.D1); BLOCKED-CA values are proven to raise rather than guess."""

from decimal import Decimal

import pytest

from app.core.money import Paise
from app.domains.payables import payables_calc as p

FIFTY_L = Paise.from_rupees(50_00_000)
TWENTY_K = Paise.from_rupees(20_000)


# ---- 194Q: 0.1% on purchases exceeding ₹50L/vendor/FY ----
def test_194q_above_threshold_taxes_only_the_excess():
    # ₹60L purchase, no prior YTD -> excess = ₹10L, TDS = 0.1% = ₹1,000
    res = p.tds_194q(Paise.from_rupees(60_00_000))
    assert res["applicable"] is True
    assert res["rate"] == Decimal("0.1")
    assert res["taxable_paise"] == Paise.from_rupees(10_00_000)
    assert res["tds_paise"] == Paise.from_rupees(1_000)


def test_194q_at_50L_boundary_no_tds():
    # aggregate lands at exactly ₹50L -> not exceeding -> no deduction
    res = p.tds_194q(FIFTY_L)
    assert res["applicable"] is False
    assert res["taxable_paise"] == 0
    assert res["tds_paise"] == 0


def test_194q_crossing_via_aggregate_taxes_slice_above_50L():
    # ₹40L already booked, this ₹20L payment crosses ₹50L -> excess = ₹10L -> ₹1,000
    res = p.tds_194q(Paise.from_rupees(20_00_000), aggregate_ytd=Paise.from_rupees(40_00_000))
    assert res["taxable_paise"] == Paise.from_rupees(10_00_000)
    assert res["tds_paise"] == Paise.from_rupees(1_000)


def test_194q_primacy_suppresses_tcs_206c_1h():
    # TDS primacy: when 194Q applies, TCS 206C(1H) does not
    assert p.tds_194q(Paise.from_rupees(60_00_000))["tcs_206c_1h_suppressed"] is True
    assert p.tds_194q(FIFTY_L)["tcs_206c_1h_suppressed"] is False


# ---- 194T: 10% on partner payments exceeding ₹20,000 ----
def test_194t_above_threshold():
    res = p.tds_194t(Paise.from_rupees(50_000))
    assert res["applicable"] is True
    assert res["rate"] == Decimal("10")
    assert res["tds_paise"] == Paise.from_rupees(5_000)  # 10% of full ₹50k


def test_194t_at_20k_boundary_no_tds():
    res = p.tds_194t(TWENTY_K)
    assert res["applicable"] is False
    assert res["tds_paise"] == 0


def test_194t_crossing_via_aggregate():
    # ₹15k prior + ₹10k -> ₹25k > ₹20k -> 10% of the ₹10k payment
    res = p.tds_194t(Paise.from_rupees(10_000), aggregate_ytd=Paise.from_rupees(15_000))
    assert res["applicable"] is True
    assert res["tds_paise"] == Paise.from_rupees(1_000)


# ---- TCS s.394: structure only; rate + threshold BLOCKED-CA ----
def test_tcs_394_blocked_ca_rate_raises():
    with pytest.raises(ValueError, match="BLOCKED-CA"):
        p.tcs_394_goods(Paise.from_rupees(60_00_000), threshold=FIFTY_L)


def test_tcs_394_blocked_ca_threshold_raises():
    with pytest.raises(ValueError, match="BLOCKED-CA"):
        p.tcs_394_goods(Paise.from_rupees(60_00_000), rate=Decimal("0.1"))


def test_tcs_394_structure_computes_with_supplied_values():
    # supplying CA-sourced values (here mirroring the 194Q shape) exercises the excess mechanic
    res = p.tcs_394_goods(Paise.from_rupees(60_00_000), rate=Decimal("0.1"), threshold=FIFTY_L)
    assert res["taxable_paise"] == Paise.from_rupees(10_00_000)
    assert res["tcs_paise"] == Paise.from_rupees(1_000)


# ---- 206AA / 206AB overlay: BLOCKED-CA floors, structure only ----
def test_higher_rate_passthrough_with_pan_and_filer():
    r = p.apply_higher_rate(Decimal("10"), pan_available=True, is_non_filer=False)
    assert r == Decimal("10")


def test_higher_rate_no_pan_without_floor_raises():
    with pytest.raises(ValueError, match="BLOCKED-CA"):
        p.apply_higher_rate(Decimal("10"), pan_available=False, is_non_filer=False)


def test_higher_rate_non_filer_without_floor_raises():
    with pytest.raises(ValueError, match="BLOCKED-CA"):
        p.apply_higher_rate(Decimal("10"), pan_available=True, is_non_filer=True)


def test_higher_rate_takes_highest_of_base_and_supplied_floors():
    # base 10, no-PAN floor 20, non-filer floor 15 -> 20 wins
    r = p.apply_higher_rate(
        Decimal("10"),
        pan_available=False,
        is_non_filer=True,
        no_pan_rate=Decimal("20"),
        non_filer_rate=Decimal("15"),
    )
    assert r == Decimal("20")
