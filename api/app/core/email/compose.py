"""Pure composers for the domain emails (PRD §6.2–6.4): turn raw domain data into the
JSON-able context each template renders. No DB/Mahsa/network — fully unit-testable."""

from __future__ import annotations

from typing import Any


def compose_compliance_alert(alerts: list[dict], as_of: str) -> dict[str, Any]:
    """Split compliance-calendar alerts into overdue vs upcoming for the alert email."""
    overdue = [a for a in alerts if a.get("label") == "OVERDUE"]
    upcoming = [a for a in alerts if a.get("label") != "OVERDUE"]
    return {
        "as_of": as_of,
        "overdue": sorted(overdue, key=lambda a: a.get("days_overdue", 0), reverse=True),
        "upcoming": sorted(upcoming, key=lambda a: a["due_date"]),
        "total": len(alerts),
    }


def compose_payroll_approval(
    run: dict, entries: list[dict], *, validation_status: str, mahsa_note: str = ""
) -> dict[str, Any]:
    """Payroll-run approval email context: totals + per-employee breakdown + Mahsa note."""
    return {
        "month_year": run["month_year"],
        "employee_count": run["employee_count"],
        "total_gross": run["total_gross"],
        "total_deductions": run["total_deductions"],
        "total_net": run["total_net"],
        "total_pf_employer": run["total_pf_employer"],
        "total_esi_employer": run["total_esi_employer"],
        "validation_status": validation_status,
        "mahsa_note": mahsa_note,
        "entries": entries,
    }


def compose_investor_update(
    period: str, kpis: dict, cap_table: dict, *, highlights: list[str] | None = None
) -> dict[str, Any]:
    """Quarterly investor update: headline KPIs + cap-table summary + highlights."""
    return {
        "period": period,
        "cash": kpis.get("cash", 0),
        "net_burn": kpis.get("net_burn", 0),
        "runway_fmt": kpis.get("runway_fmt", "—"),
        "ar": kpis.get("ar", 0),
        "cap_table": {
            "total_shares": cap_table.get("total_shares", 0),
            "ownership": cap_table.get("pct", {}),
        },
        "highlights": highlights or [],
    }
