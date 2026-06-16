"""Double-entry accounting checks — balance, trial balance, P&L, balance sheet, depreciation."""

from app.core.money import Paise
from app.domains.ledger import ledger_calc as lc

# A small but complete set of books (see comment in test_statements):
#   Cash(asset), Capital(equity), Creditors(liability), Sales(income), Rent(expense)
_ROWS = [
    {"account_type": "asset", "debit": Paise.from_rupees(8000), "credit": 0},  # Cash net
    {"account_type": "equity", "debit": 0, "credit": Paise.from_rupees(3000)},  # Capital
    {"account_type": "liability", "debit": 0, "credit": Paise.from_rupees(2000)},  # Creditors
    {"account_type": "income", "debit": 0, "credit": Paise.from_rupees(4000)},  # Sales
    {"account_type": "expense", "debit": Paise.from_rupees(1000), "credit": 0},  # Rent
]


def test_is_balanced():
    assert lc.is_balanced(
        [
            {"debit": Paise.from_rupees(100), "credit": 0},
            {"debit": 0, "credit": Paise.from_rupees(100)},
        ]
    )
    assert not lc.is_balanced(
        [
            {"debit": Paise.from_rupees(100), "credit": 0},
            {"debit": 0, "credit": Paise.from_rupees(90)},
        ]
    )


def test_trial_balance_ties_out():
    tb = lc.trial_balance(_ROWS)
    assert tb["total_debit"] == Paise.from_rupees(9000)  # Cash 8000 + Rent 1000
    assert tb["total_credit"] == Paise.from_rupees(9000)  # 3000 + 2000 + 4000
    assert tb["diff"] == 0
    assert tb["balanced"] is True


def test_profit_and_loss():
    pnl = lc.profit_and_loss(_ROWS)
    assert pnl["income"] == Paise.from_rupees(4000)
    assert pnl["expense"] == Paise.from_rupees(1000)
    assert pnl["net_profit"] == Paise.from_rupees(3000)


def test_balance_sheet_equation_holds():
    bs = lc.balance_sheet(_ROWS)
    # assets 8000 == liabilities 2000 + equity 3000 + retained profit 3000
    assert bs["assets"] == Paise.from_rupees(8000)
    assert bs["liabilities"] == Paise.from_rupees(2000)
    assert bs["equity"] == Paise.from_rupees(3000)
    assert bs["retained_profit"] == Paise.from_rupees(3000)
    assert bs["balanced"] is True


def test_depreciation_methods():
    # SLM: (₹1,00,000 - ₹10,000) / 9 = ₹10,000/yr
    slm = lc.slm_annual(Paise.from_rupees(100000), Paise.from_rupees(10000), 9)
    assert slm == Paise.from_rupees(10000)
    # WDV: ₹1,00,000 × 10% = ₹10,000
    assert lc.wdv_annual(Paise.from_rupees(100000), 10.0) == Paise.from_rupees(10000)
