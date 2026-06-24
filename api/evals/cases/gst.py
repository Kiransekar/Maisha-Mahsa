"""GST eval cases. A late GSTR-3B must trip Mahsa rule GST-001 and be cited to its statute
(CGST Act 2017, Sec 47 / Rule 61) — this is the case that exercises the citation scorer."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models.gst import GstReturn
from app.llm.schema import ActionClaim, RuleAssertion

from ..types import EvalCase, Expectation

# Due 20 Jun; asked on 10 Jul → 20 days late.
_AS_OF = date(2026, 7, 10)


def _seed_late_3b(session: Session) -> None:
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-05",
            due_date="2026-06-20",
            status="pending",
        )
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="gst-3b-late",
        domain="gst",
        query="Is our GSTR-3B filing on time?",
        seed=_seed_late_3b,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"gstr3b_days_late": "20"},
            citations=["CGST Act 2017 / Sec 47 / Rule 61"],
            expected_status="red",  # GST-001 severity: block
        ),
        stub_claim=ActionClaim(
            domain="gst",
            narrative="GSTR-3B for 2026-05 is 20 days overdue; late fee under Sec 47 accrues.",
            claims={"gstr3b_days_late": "20"},
            rule_assertions=[
                RuleAssertion(
                    rule_id="GST-001", statute="CGST Act 2017", section="Sec 47 / Rule 61"
                )
            ],
        ),
    ),
]
