import pytest

from app.core.money import Paise
from app.db.models.ledger import FixedAsset
from app.domains.ledger.service import LedgerService


def _books(session):
    """Set up a tiny but complete set of books and return the LedgerService + account ids."""
    svc = LedgerService()
    ids = {
        "cash": svc.create_account(session, code="1000", name="Cash", account_type="asset"),
        "capital": svc.create_account(session, code="3000", name="Capital", account_type="equity"),
        "creditors": svc.create_account(
            session, code="2000", name="Creditors", account_type="liability"
        ),
        "sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
        "rent": svc.create_account(session, code="5000", name="Rent", account_type="expense"),
    }

    def je(desc, dr_acct, cr_acct, amt):
        svc.post_journal_entry(
            session,
            entry_date="2026-05-01",
            description=desc,
            lines=[
                {"account_id": ids[dr_acct], "debit": Paise.from_rupees(amt), "credit": 0},
                {"account_id": ids[cr_acct], "debit": 0, "credit": Paise.from_rupees(amt)},
            ],
        )

    je("capital introduced", "cash", "capital", 3000)
    je("loan taken", "cash", "creditors", 2000)
    je("cash sale", "cash", "sales", 4000)
    je("paid rent", "rent", "cash", 1000)
    return svc


def test_post_balanced_entry_and_statements(session):
    svc = _books(session)
    tb = svc.trial_balance(session)
    assert tb["balanced"] is True and tb["diff"] == 0
    assert svc.profit_and_loss(session)["net_profit"] == Paise.from_rupees(3000)
    bs = svc.balance_sheet(session)
    assert bs["balanced"] is True
    assert bs["assets"] == Paise.from_rupees(8000)


def test_unbalanced_entry_is_rejected(session):
    svc = LedgerService()
    cash = svc.create_account(session, code="1000", name="Cash", account_type="asset")
    sales = svc.create_account(session, code="4000", name="Sales", account_type="income")
    with pytest.raises(ValueError, match="not balanced"):
        svc.post_journal_entry(
            session,
            entry_date="2026-05-01",
            description="bad",
            lines=[
                {"account_id": cash, "debit": Paise.from_rupees(100), "credit": 0},
                {"account_id": sales, "debit": 0, "credit": Paise.from_rupees(90)},
            ],
        )


def test_invalid_account_type_rejected(session):
    svc = LedgerService()
    with pytest.raises(ValueError, match="invalid account_type"):
        svc.create_account(session, code="9", name="Bogus", account_type="liabilities")


def test_depreciation(session):
    svc = LedgerService()
    slm = FixedAsset(
        asset_name="Laptop",
        purchase_date="2026-04-01",
        purchase_cost=Paise.from_rupees(100000),
        salvage_value=Paise.from_rupees(10000),
        useful_life_years=9,
        depreciation_method="slm",
        wdv=Paise.from_rupees(100000),
    )
    session.add(slm)
    session.flush()
    assert svc.annual_depreciation(session, slm.id) == Paise.from_rupees(10000)


def test_build_snapshot_balanced_books_diff_zero(session):
    svc = _books(session)
    snap = svc.build_snapshot(session)
    assert snap["metrics"]["trial_balance_diff_paise"] == 0
    assert snap["metrics"]["net_profit_paise"] == Paise.from_rupees(3000)
