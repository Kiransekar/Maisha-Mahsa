"""Equity: share certificates, rights-issue entitlement, buyback compliance
(features share_certificates / rights_buyback)."""

from app.core.money import Paise
from app.db.models.equity import Shareholder
from app.domains.equity import equity_calc
from app.domains.equity.service import EquityService


def test_share_certificates_allocates_distinctive_numbers():
    holders = [
        {"name": "Founder A", "shares": 5000},
        {"name": "Investor X", "shares": 2000, "form": "physical"},
        {"name": "Empty", "shares": 0},  # skipped
    ]
    certs = equity_calc.share_certificates(holders)
    assert len(certs) == 2
    assert certs[0]["distinctive_from"] == 1 and certs[0]["distinctive_to"] == 5000
    assert certs[1]["distinctive_from"] == 5001 and certs[1]["distinctive_to"] == 7000
    assert certs[1]["form"] == "physical"
    assert certs[0]["certificate_no"] == "SC-0001"


def test_rights_entitlement_is_pro_rata():
    holders = [{"name": "A", "shares": 6000}, {"name": "B", "shares": 4000}]
    ent = equity_calc.rights_entitlement(holders, 1000)
    assert {e["name"]: e["entitlement"] for e in ent} == {"A": 600, "B": 400}


def test_buyback_within_limits_permitted():
    res = equity_calc.buyback_compliance(
        paid_up_capital=Paise.from_rupees(10_000_000),
        free_reserves=Paise.from_rupees(30_000_000),
        buyback_amount=Paise.from_rupees(5_000_000),  # < 25% of 4cr = 1cr
        shares_bought_back=100,
        total_shares=1000,  # 10% < 25%
        post_buyback_debt=Paise.from_rupees(1_000_000),
        post_buyback_equity=Paise.from_rupees(2_000_000),  # 0.5:1 < 2:1
    )
    assert res["permitted"] is True and res["reasons"] == []


def test_buyback_breaches_flagged():
    res = equity_calc.buyback_compliance(
        paid_up_capital=Paise.from_rupees(1_000_000),
        free_reserves=Paise.from_rupees(1_000_000),
        buyback_amount=Paise.from_rupees(1_500_000),  # > 25% of 20L = 5L
        shares_bought_back=400,
        total_shares=1000,  # 40% > 25%
        post_buyback_debt=Paise.from_rupees(5_000_000),
        post_buyback_equity=Paise.from_rupees(1_000_000),  # 5:1 > 2:1
    )
    assert res["permitted"] is False
    assert len(res["reasons"]) == 3


def test_service_share_certificates_from_db(session):
    for name, cat, shares in (("Founder A", "founder", 5000), ("Angel", "investor", 1000)):
        session.add(Shareholder(name=name, category=cat, shares_held=shares))
    session.flush()
    certs = EquityService().share_certificates(session)
    assert len(certs) == 2
    assert certs[-1]["distinctive_to"] == 6000
