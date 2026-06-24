"""F5 CFO strategy: runway scenarios, cap table, investor-update payload."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.core.strategy import cap_table, investor_update, run_scenario
from app.db.models.treasury import BankAccount, BankTransaction

_AS_OF = date(2026, 6, 30)


def _seed_treasury(session: Session) -> None:
    acct = BankAccount(
        bank_name="HDFC", account_number="1", ifsc="HDFC0000001",
        opening_balance=Paise.from_rupees(1200000), current_balance=Paise.from_rupees(1200000),
    )
    session.add(acct)
    session.flush()
    # ₹9,00,000 spent and ₹3,00,000 received in the quarter -> ₹2,00,000/mo net burn -> 6.0 mo
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-15",
                                debit=Paise.from_rupees(900000), credit=0))
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-05-16",
                                debit=0, credit=Paise.from_rupees(300000)))
    session.flush()


def test_base_scenario_matches_current_runway(session: Session) -> None:
    _seed_treasury(session)
    s = run_scenario(session, _AS_OF)  # base case
    assert s.monthly_net_change_paise == -Paise.from_rupees(200000)  # net burn ₹2,00,000
    assert s.runway_months == 6.0


def test_revenue_uplift_extends_runway(session: Session) -> None:
    _seed_treasury(session)
    base = run_scenario(session, _AS_OF, revenue_mult=1.0)
    up = run_scenario(session, _AS_OF, revenue_mult=1.5)
    # more revenue -> smaller burn -> longer (or infinite) runway
    assert up.monthly_net_change_paise > base.monthly_net_change_paise
    assert (up.runway_months is None) or (up.runway_months > base.runway_months)


def test_extra_cost_shortens_runway(session: Session) -> None:
    _seed_treasury(session)
    base = run_scenario(session, _AS_OF)
    worse = run_scenario(session, _AS_OF, extra_cost_paise=Paise.from_rupees(100000))
    assert worse.runway_months is not None and base.runway_months is not None
    assert worse.runway_months < base.runway_months


def test_investor_update_payload(session: Session) -> None:
    _seed_treasury(session)
    upd = investor_update(session, _AS_OF)
    assert upd["period"] == "2026-Q2"
    assert upd["cash"] == Paise.from_rupees(1200000)
    assert "cap_table" in upd


def test_cap_table_empty_is_safe(session: Session) -> None:
    assert cap_table(session)["total_shares"] == 0
