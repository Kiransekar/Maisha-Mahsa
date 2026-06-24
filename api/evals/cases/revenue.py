"""Revenue eval cases. Ground truth mirrors the validated values in
``tests/unit/revenue/test_revenue_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.db.models.revenue import Customer
from app.domains.revenue.service import RevenueService
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_missing_irn(session: Session) -> None:
    cust = Customer(name="Acme", state="MH", payment_terms=30)
    session.add(cust)
    session.flush()
    RevenueService().create_invoice(
        session,
        invoice_number="INV-9",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=[{"description": "Service", "quantity": 1, "rate": Paise.from_rupees(100000),
                "hsn_code": "9983"}],
        gst_rate=18,
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="revenue-missing-irn",
        domain="revenue",
        query="What's our trailing turnover and are any invoices missing an IRN?",
        seed=_seed_missing_irn,
        as_of=_AS_OF,
        expect=Expectation(
            claims={
                "annual_turnover_rupees": "118000",  # ₹1,00,000 + 18% GST
                "einvoice_missing": "1",
                "monthly_revenue_paise": "983333",  # 11800000 paise // 12
            },
        ),
        stub_claim=ActionClaim(
            domain="revenue",
            narrative="One invoice (₹1,18,000 incl. GST) issued; it has no IRN.",
            claims={
                "annual_turnover_rupees": "118000",
                "einvoice_missing": "1",
                "monthly_revenue_paise": "983333",
            },
        ),
    ),
]
