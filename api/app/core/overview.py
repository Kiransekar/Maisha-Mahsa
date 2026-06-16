"""Headline KPIs and the compliance calendar for the dashboard. These are direct DB reads
through the domain services (no Mahsa needed), so the KPI strip renders even when the
sidecar is down."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.domains.compliance.service import ComplianceService
from app.domains.payables.service import PayablesService
from app.domains.revenue.service import RevenueService
from app.domains.treasury.service import TreasuryService


def _fmt(paise: int) -> str:
    return Paise(int(paise)).format_inr()


def collect_kpis(session: Session, as_of: date) -> dict[str, Any]:
    """Cash / net burn / runway / AR / AP headline figures (paise + formatted)."""
    tm = TreasuryService().metrics(session, as_of)
    ar = RevenueService().ar_aging(session, as_of)["total_outstanding"]
    ap = PayablesService().ap_aging(session, as_of)["total_outstanding"]
    runway = tm["runway_months"]
    return {
        "cash": tm["cash_paise"],
        "cash_fmt": _fmt(tm["cash_paise"]),
        "net_burn": tm["net_burn_paise"],
        "net_burn_fmt": _fmt(tm["net_burn_paise"]),
        "runway_months": runway,
        "runway_fmt": ("∞" if runway is None else f"{runway:g} mo"),
        "ar": ar,
        "ar_fmt": _fmt(ar),
        "ap": ap,
        "ap_fmt": _fmt(ap),
        "accounts": tm["account_count"],
    }


def upcoming_deadlines(session: Session, as_of: date) -> list[dict[str, Any]]:
    """Compliance-calendar alerts due now (T-7/T-1/T-0) or overdue."""
    return ComplianceService().alerts(session, as_of)
