from decimal import Decimal

from app.core.money import Paise


def test_from_rupees_is_exact():
    assert Paise.from_rupees("150.50") == 15050
    assert Paise.from_rupees(1000) == 100000
    assert Paise.from_rupees(Decimal("99.99")) == 9999


def test_float_input_does_not_leak_binary_error():
    # 0.1 + 0.2 == 0.30000000000000004 as float, but routed via Decimal(str(...)) it is exact.
    assert Paise.from_rupees(0.1) == 10
    assert Paise.from_rupees(0.1) + Paise.from_rupees(0.2) == 30


def test_rupees_property_is_decimal():
    assert Paise(15050).rupees == Decimal("150.50")


def test_indian_grouping_format():
    assert Paise.from_rupees(1234567).format_inr() == "₹12,34,567.00"
    assert Paise.from_rupees(1000).format_inr() == "₹1,000.00"
    assert Paise.from_rupees(50).format_inr() == "₹50.00"
    assert Paise(-15050).format_inr() == "-₹150.50"
