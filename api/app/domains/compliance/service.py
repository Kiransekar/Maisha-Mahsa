"""Compliance service: the statutory calendar that aggregates every deadline the other
modules track (GST 20th, TDS 7th, PF/ESI 15th, PT, ROC) into one view, plus the compliance
health snapshot for Mahsa. Deterministic — ``as_of`` injected."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.shared import ComplianceCalendar
from app.domains.compliance import compliance_calc
from app.domains.compliance.manifest import MANIFEST

# Standard monthly statutory deadlines: (domain, form_name, day-of-following-month).
_MONTHLY_DEADLINES = [
    ("tds", "TDS deposit", 7),
    ("pf", "PF ECR", 15),
    ("esi", "ESI contribution", 15),
    ("gst", "GSTR-3B", 20),
    ("pt", "Professional Tax", 21),
]


def _next_month(month: str) -> tuple[int, int]:
    year, m = (int(p) for p in month.split("-"))
    return (year + 1, 1) if m == 12 else (year, m + 1)


class ComplianceService(BaseDomainService):
    domain = "compliance"
    keywords = (
        "roc",
        "aoc-4",
        "mgt-7",
        "compliance",
        "filing",
        "calendar",
        "deadline",
        "due date",
        "secretarial",
    )
    manifest = MANIFEST

    # ---- calendar -------------------------------------------------------------------

    def add_deadline(
        self,
        session: Session,
        *,
        domain: str,
        form_name: str,
        due_date: str,
        filing_period: str | None = None,
    ) -> int:
        row = ComplianceCalendar(
            domain=domain,
            form_name=form_name,
            due_date=due_date,
            filing_period=filing_period,
        )
        session.add(row)
        session.flush()
        return row.id

    def seed_month(self, session: Session, month: str) -> list[int]:
        """Seed the standard statutory deadlines for the liabilities of ``month`` (YYYY-MM),
        all due in the following month."""
        ny, nm = _next_month(month)
        ids = []
        for domain, form, day in _MONTHLY_DEADLINES:
            due = date(ny, nm, day).isoformat()
            ids.append(
                self.add_deadline(
                    session,
                    domain=domain,
                    form_name=f"{form} ({month})",
                    due_date=due,
                    filing_period=month,
                )
            )
        return ids

    def mark_filed(
        self,
        session: Session,
        deadline_id: int,
        *,
        filed_date: str,
        acknowledgement: str | None = None,
    ) -> None:
        row = session.get(ComplianceCalendar, deadline_id)
        if row is None:
            raise ValueError(f"compliance deadline {deadline_id} not found")
        row.status = "filed"
        row.filed_date = filed_date
        row.acknowledgement = acknowledgement
        session.flush()

    def _entries(self, session: Session) -> list[dict]:
        return [
            {
                "domain": e.domain,
                "form_name": e.form_name,
                "due_date": e.due_date,
                "status": e.status,
            }
            for e in session.scalars(select(ComplianceCalendar)).all()
        ]

    def alerts(self, session: Session, as_of: date) -> list[dict[str, Any]]:
        return compliance_calc.alerts(self._entries(session), as_of)

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        entries = self._entries(session)
        overdue = compliance_calc.overdue_count(entries, anchor)
        health = compliance_calc.domain_health(entries, anchor)

        return {
            "as_of": anchor.isoformat(),
            "overdue_filings": overdue,  # drives global COMPLIANCE-002
            "metrics": {
                "roc_filing_status": health["roc"],
                "gst_filing_status": health["gst"],
                "tds_filing_status": health["tds"],
                "pf_filing_status": health["pf"],
                "esi_filing_status": health["esi"],
                "pt_filing_status": health["pt"],
                "secretarial_score": 1.0,
                "audit_readiness": 1.0,
            },
        }
