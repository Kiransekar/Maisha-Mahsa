"""Treasury eval cases. Money is integer paise; ground truth is computed by hand from the
seed and mirrored in each ``stub_claim`` (the canned answer the stub producer returns in
P0-①). The build_snapshot path under test lives in ``app.domains.treasury.service``."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

# as_of for the windowed metrics; the 3-month window ending here is 2026-03-30 .. 2026-06-30.
_AS_OF = date(2026, 6, 30)


def _seed_healthy(session: Session) -> None:
    """₹12,00,000 cash; ₹9,00,000 spent and ₹3,00,000 received in the trailing quarter →
    ₹3,00,000/mo burn, ₹1,00,000/mo revenue, ₹2,00,000/mo net burn → 6.0 months runway."""
    acct = BankAccount(
        bank_name="HDFC",
        account_number="0001",
        ifsc="HDFC0000001",
        opening_balance=Paise.from_rupees(1200000),
        current_balance=Paise.from_rupees(1200000),
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-05-15",
            description="Quarter spend",
            debit=Paise.from_rupees(900000),
            credit=0,
        )
    )
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-05-16",
            description="Quarter revenue",
            debit=0,
            credit=Paise.from_rupees(300000),
        )
    )


def _seed_empty(session: Session) -> None:
    """No accounts, no transactions: net burn is zero, so runway is undefined — the model
    must abstain rather than invent a number."""
    # intentionally seeds nothing


CASES: list[EvalCase] = [
    EvalCase(
        id="treasury-runway-healthy",
        domain="treasury",
        query="What's our cash position and runway?",
        seed=_seed_healthy,
        as_of=_AS_OF,
        expect=Expectation(
            claims={
                "cash_paise": str(Paise.from_rupees(1200000)),  # 120000000
                "monthly_burn_paise": str(Paise.from_rupees(300000)),  # 30000000
                "monthly_revenue_paise": str(Paise.from_rupees(100000)),  # 10000000
                "runway_months": "6.0",
            },
            expected_status="green",
        ),
        stub_claim=ActionClaim(
            domain="treasury",
            narrative="Cash ₹12,00,000; net burn ₹2,00,000/mo gives ~6.0 months runway.",
            claims={
                "cash_paise": "120000000",
                "monthly_burn_paise": "30000000",
                "monthly_revenue_paise": "10000000",
                "runway_months": "6.0",
            },
        ),
    ),
    EvalCase(
        id="treasury-no-data-abstain",
        domain="treasury",
        query="What's our runway?",
        seed=_seed_empty,
        as_of=_AS_OF,
        expect=Expectation(must_abstain=True),
        stub_claim=ActionClaim(
            domain="treasury",
            narrative="No bank data on record — cannot compute runway. Connect an account.",
            abstained=True,
        ),
    ),
]
