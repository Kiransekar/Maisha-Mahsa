"""Expense computation checks — policy limits, petty cash, analytics, receipt parsing."""

from app.core.money import Paise
from app.domains.expense import expense_calc as ec


def test_policy_check():
    over = ec.check_policy("meals", Paise.from_rupees(3000))  # limit ₹2,000
    assert over["over_policy"] is True
    assert over["excess"] == Paise.from_rupees(1000)
    ok = ec.check_policy("meals", Paise.from_rupees(1500))
    assert ok["over_policy"] is False
    # unknown category -> unlimited
    assert ec.check_policy("misc", Paise.from_rupees(999999))["over_policy"] is False


def test_petty_cash_threshold():
    assert ec.is_petty_cash_eligible(Paise.from_rupees(10000)) is True
    assert ec.is_petty_cash_eligible(Paise.from_rupees(10001)) is False


def test_category_spend():
    claims = [
        {"category": "meals", "amount": Paise.from_rupees(1000)},
        {"category": "meals", "amount": Paise.from_rupees(500)},
        {"category": "travel", "amount": Paise.from_rupees(20000)},
    ]
    spend = ec.category_spend(claims)
    assert spend["meals"] == Paise.from_rupees(1500)
    assert spend["travel"] == Paise.from_rupees(20000)


def test_parse_receipt_extracts_total_gstin_date():
    text = (
        "TASTY CAFE\nGSTIN: 27AAPFU0939F1ZV\nDate: 2026-05-10\n"
        "Coffee  ₹250.00\nSandwich  ₹350.00\nTotal  ₹600.00"
    )
    parsed = ec.parse_receipt(text)
    assert parsed["amount_paise"] == Paise.from_rupees(600)  # largest figure = total
    assert parsed["gstin"] == "27AAPFU0939F1ZV"
    assert parsed["date"] == "2026-05-10"


def test_parse_receipt_handles_no_matches():
    parsed = ec.parse_receipt("illegible scan")
    assert parsed["amount_paise"] is None
    assert parsed["gstin"] is None
