"""Tax eval cases. TDS deducted in April is due by 7 May; unpaid at 16 Jun it is 40 days
overdue. Ground truth mirrors ``tests/unit/tax/test_tax_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.db.models.tax import TdsEntry
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_overdue_tds(session: Session) -> None:
    session.add(
        TdsEntry(
            deductee_name="X",
            section="194J",
            payment_date="2026-04-10",
            payment_amount=Paise.from_rupees(50000),
            tds_amount=Paise.from_rupees(5000),
            total_tds=Paise.from_rupees(5000),
        )
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="tax-tds-overdue",
        domain="tax",
        query="Is any TDS deposit overdue?",
        seed=_seed_overdue_tds,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"tds_days_overdue": "40"},
        ),
        stub_claim=ActionClaim(
            domain="tax",
            narrative="TDS for April is 40 days past its 7 May deposit deadline.",
            claims={"tds_days_overdue": "40"},
        ),
    ),
]
