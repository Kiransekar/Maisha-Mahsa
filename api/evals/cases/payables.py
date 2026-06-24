"""Payables eval cases. An MSME bill unpaid past 45 days must trip PAYABLES-001 (MSMED Act
2006). Ground truth mirrors ``tests/unit/payables/test_payables_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.db.models.payables import Vendor
from app.domains.payables.service import PayablesService
from app.llm.schema import ActionClaim, RuleAssertion

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_msme_overdue(session: Session) -> None:
    v = Vendor(name="Vend", payee_type="company", msme_status=1, payment_terms=30)
    session.add(v)
    session.flush()
    # Bill dated 1 Apr, unpaid at 16 Jun -> 76 days > 45-day MSME limit.
    PayablesService().create_bill(
        session,
        bill_number="B3",
        vendor_id=v.id,
        bill_date="2026-04-01",
        subtotal=Paise.from_rupees(20000),
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="payables-msme-overdue",
        domain="payables",
        query="Are we breaching any MSME payment deadlines?",
        seed=_seed_msme_overdue,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"msme_max_days_unpaid": "76"},
            citations=["MSMED Act 2006 / Sec 15-16"],
            expected_status="yellow",
        ),
        stub_claim=ActionClaim(
            domain="payables",
            narrative="An MSME vendor bill is 76 days unpaid — past the 45-day statutory limit.",
            claims={"msme_max_days_unpaid": "76"},
            rule_assertions=[
                RuleAssertion(rule_id="PAYABLES-001", statute="MSMED Act 2006", section="Sec 15-16")
            ],
        ),
    ),
]
