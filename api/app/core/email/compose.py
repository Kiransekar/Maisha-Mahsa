"""Pure composers for the domain emails (PRD §6.2–6.4): turn raw domain data into the
JSON-able context each template renders. No DB/Mahsa/network — fully unit-testable."""

from __future__ import annotations

from typing import Any

_DUNNING_TONE = {
    "T-7": "a friendly heads-up — your invoice is due in a week",
    "T-3": "a reminder — your invoice is due in 3 days",
    "T-1": "your invoice is due tomorrow",
    "T+1": "your invoice is now overdue",
    "T+7": "your invoice is 7 days overdue — please arrange payment",
}


def compose_dunning(item: dict, as_of: str) -> dict[str, Any]:
    """Dunning-reminder email context for one outstanding invoice. ``item`` comes from
    ``RevenueService.pending_dunning`` ({invoice_number, customer_name, outstanding, due_date,
    stage})."""
    stage = item["stage"]
    return {
        "as_of": as_of,
        "invoice_number": item["invoice_number"],
        "customer_name": item["customer_name"],
        "outstanding": int(item["outstanding"]),
        "due_date": item["due_date"],
        "stage": stage,
        "message": _DUNNING_TONE.get(stage, "your invoice payment is due"),
        "overdue": stage.startswith("T+"),
    }


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
