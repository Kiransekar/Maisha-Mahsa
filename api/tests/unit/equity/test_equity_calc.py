"""Cap-table & equity computation checks — ownership, ESOP %, SAFE conversion, dilution."""

from app.core.money import Paise
from app.domains.equity import equity_calc as e


def test_ownership_percentages():
    holders = [
        {"category": "founder", "shares": 700000},
        {"category": "investor", "shares": 200000},
        {"category": "esop", "shares": 100000},
    ]
    cap = e.ownership(holders)
    assert cap["total_shares"] == 1000000
    assert cap["pct"]["founder"] == 0.7
    assert cap["pct"]["investor"] == 0.2
    assert cap["pct"]["esop"] == 0.1


def test_esop_pool_pct():
    assert e.esop_pool_pct(100000, 1000000) == 0.1
    assert e.esop_pool_pct(0, 0) == 0.0


def test_safe_conversion_cap_beats_discount():
    # cap price = ₹5Cr / 10,00,000 = ₹50/share; discount price = ₹100 × 0.8 = ₹80/share.
    # cap is cheaper -> investor converts at ₹50 -> ₹50,00,000 / ₹50 = 1,00,000 shares.
    res = e.safe_conversion(
        investment=Paise.from_rupees(5000000),
        valuation_cap=Paise.from_rupees(50000000),
        discount_rate=0.20,
        round_price_per_share=Paise.from_rupees(100),
        pre_round_shares=1000000,
    )
    assert res["conversion_price_paise"] == Paise.from_rupees(50)
    assert res["shares_issued"] == 100000


def test_safe_conversion_discount_when_no_cap():
    # no cap -> discount price ₹80 -> ₹8,00,000 / ₹80 = 10,000 shares
    res = e.safe_conversion(
        investment=Paise.from_rupees(800000),
        valuation_cap=None,
        discount_rate=0.20,
        round_price_per_share=Paise.from_rupees(100),
        pre_round_shares=1000000,
    )
    assert res["conversion_price_paise"] == Paise.from_rupees(80)
    assert res["shares_issued"] == 10000


def test_post_round_dilution():
    # founder 7,00,000 of 10,00,000 (70%); issue 2,50,000 new -> 7,00,000 / 12,50,000 = 56%
    assert e.post_round_ownership(700000, 1000000, 250000) == 0.56
