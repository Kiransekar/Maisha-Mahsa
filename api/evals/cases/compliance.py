"""Compliance eval cases. An unfiled GSTR-3B past its due date is one overdue filing, which
trips the global COMPLIANCE-002 rule. Ground truth mirrors
``tests/unit/compliance/test_compliance_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domains.compliance.service import ComplianceService
from app.llm.schema import ActionClaim, RuleAssertion

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_overdue_filing(session: Session) -> None:
    ComplianceService().add_deadline(
        session,
        domain="gst",
        form_name="GSTR-3B (Apr)",
        due_date="2026-05-20",
        filing_period="2026-04",
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="compliance-overdue-filing",
        domain="compliance",
        query="Are any statutory filings overdue?",
        seed=_seed_overdue_filing,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"overdue_filings": "1"},
            citations=["Various (see compliance calendar) / —"],
            expected_status="yellow",
        ),
        stub_claim=ActionClaim(
            domain="compliance",
            narrative="One filing (GSTR-3B for Apr) is overdue.",
            claims={"overdue_filings": "1"},
            rule_assertions=[
                RuleAssertion(
                    rule_id="COMPLIANCE-002",
                    statute="Various (see compliance calendar)",
                    section="—",
                )
            ],
        ),
    ),
]
