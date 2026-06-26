"""Compliance-calendar logic — pure, deterministic. Operates on plain entry dicts
({domain, form_name, due_date, status}) so it is trivially testable. Time is injected
via ``as_of``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Statutory domains that map 1:1 onto the compliance sub-vector dimensions.
STATUTORY_DOMAINS = ("roc", "gst", "tds", "pf", "esi", "pt")


def mca_deadlines(*, agm_date: str) -> list[dict[str, Any]]:
    """MCA annual-filing deadlines for a private company given its AGM date (Companies Act
    2013): AOC-4 within 30 days, MGT-7 within 60; DPT-3 by 30 Jun and DIR-3 KYC by 30 Sep."""
    agm = date.fromisoformat(agm_date)
    return [
        {"domain": "roc", "form": "AOC-4", "statute": "Companies Act 2013 s.137",
         "due_date": (agm + timedelta(days=30)).isoformat()},
        {"domain": "roc", "form": "MGT-7", "statute": "Companies Act 2013 s.92",
         "due_date": (agm + timedelta(days=60)).isoformat()},
        {"domain": "roc", "form": "DPT-3", "statute": "Companies Act 2013 Rule 16",
         "due_date": f"{agm.year}-06-30"},
        {"domain": "roc", "form": "DIR-3 KYC", "statute": "Companies Act 2013 Rule 12A",
         "due_date": f"{agm.year}-09-30"},
    ]

def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    import calendar

    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# ---- Secretarial compliance (minutes / AGM / resolutions) -----------------------------


def board_meeting_compliance(meeting_dates: list[str]) -> dict[str, Any]:
    """Companies Act 2013 s.173: a company needs >=4 board meetings a year, with no gap
    exceeding 120 days between two consecutive meetings. Pure."""
    dates = sorted(date.fromisoformat(d) for d in meeting_dates)
    count_ok = len(dates) >= 4
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    max_gap = max(gaps) if gaps else 0
    gap_ok = max_gap <= 120
    reasons = []
    if not count_ok:
        reasons.append("fewer than 4 board meetings in the year")
    if len(dates) > 1 and not gap_ok:
        reasons.append(f"gap of {max_gap} days exceeds 120 between consecutive meetings")
    return {
        "compliant": count_ok and gap_ok,
        "meetings": len(dates),
        "max_gap_days": max_gap,
        "reasons": reasons,
    }


def secretarial_calendar(fy_end: str) -> list[dict[str, Any]]:
    """Annual secretarial calendar for a private company given its FY end (YYYY-MM-DD): the AGM
    (within 6 months of FY end, s.96) plus the recurring board-meeting, register and minutes
    duties spread across the year. Pure."""
    end = date.fromisoformat(fy_end)
    fy_start = _add_months(end, -12)
    items = [
        {"item": "Annual General Meeting", "statute": "Companies Act 2013 s.96",
         "due_date": _add_months(end, 6).isoformat()},
        {"item": "Maintain statutory registers", "statute": "Companies Act 2013 s.88",
         "due_date": end.isoformat()},
        {"item": "Record minutes of meetings", "statute": "Companies Act 2013 s.118",
         "due_date": end.isoformat()},
    ]
    for q in range(4):  # one board meeting target per quarter
        items.append(
            {"item": f"Board meeting Q{q + 1}", "statute": "Companies Act 2013 s.173",
             "due_date": _add_months(fy_start, q * 3 + 3).isoformat()}
        )
    return items


# ---- Audit support package ------------------------------------------------------------

AUDIT_CHECKLIST = (
    "trial_balance", "general_ledger", "bank_statements", "bank_reconciliation",
    "fixed_asset_register", "gst_returns", "tds_returns", "payroll_records",
    "invoices", "bills", "board_minutes", "cap_table",
)


def audit_support_package(available: set[str], *, audit_type: str = "statutory") -> dict[str, Any]:
    """Audit support checklist (statutory or internal): which schedules/records are ready and
    which are missing, with a readiness percentage. Pure."""
    have = set(available)
    missing = [item for item in AUDIT_CHECKLIST if item not in have]
    present = len(AUDIT_CHECKLIST) - len(missing)
    return {
        "audit_type": audit_type,
        "items": [{"item": i, "present": i in have} for i in AUDIT_CHECKLIST],
        "missing": missing,
        "readiness_pct": round(100.0 * present / len(AUDIT_CHECKLIST), 1),
    }


# ---- DPIIT Startup India recognition --------------------------------------------------

_DPIIT_MAX_TURNOVER_PAISE = 100 * 10**7 * 100  # Rs 100 crore, in paise


def dpiit_eligibility(
    *,
    incorporation_date: str,
    as_of: str,
    annual_turnover_paise: int,
    is_reconstituted: bool = False,
) -> dict[str, Any]:
    """DPIIT Startup India recognition (Notification G.S.R. 127(E)): incorporated < 10 years
    ago, annual turnover < Rs.100 crore, and not formed by splitting/reconstructing an existing
    business. Pure & deterministic (time injected via ``as_of``)."""
    inc = date.fromisoformat(incorporation_date)
    now = date.fromisoformat(as_of)
    age_years = (now - inc).days / 365.25
    age_ok = age_years < 10
    turnover_ok = int(annual_turnover_paise) < _DPIIT_MAX_TURNOVER_PAISE
    reasons = []
    if not age_ok:
        reasons.append("incorporated 10 or more years ago")
    if not turnover_ok:
        reasons.append("annual turnover is Rs.100 crore or more")
    if is_reconstituted:
        reasons.append("formed by splitting up / reconstructing an existing business")
    return {
        "eligible": age_ok and turnover_ok and not is_reconstituted,
        "age_years": round(age_years, 2),
        "reasons": reasons,
    }


# Reminder cadence (PRD §1.10): T-7, T-1, T-0.
ALERT_OFFSETS = {7: "T-7", 1: "T-1", 0: "T-0"}


def _pending(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("status") != "filed"]


def overdue_count(entries: list[dict], as_of: date) -> int:
    return sum(1 for e in _pending(entries) if date.fromisoformat(e["due_date"]) < as_of)


def domain_health(entries: list[dict], as_of: date) -> dict[str, float]:
    """1.0 when a statute has nothing overdue, else 0.0."""
    health = dict.fromkeys(STATUTORY_DOMAINS, 1.0)
    for e in _pending(entries):
        d = e.get("domain")
        if d in health and date.fromisoformat(e["due_date"]) < as_of:
            health[d] = 0.0
    return health


def alerts(entries: list[dict], as_of: date) -> list[dict[str, Any]]:
    """Reminders due exactly on ``as_of`` (T-7/T-1/T-0) plus any already overdue."""
    out: list[dict[str, Any]] = []
    for e in _pending(entries):
        delta = (date.fromisoformat(e["due_date"]) - as_of).days
        if delta < 0:
            out.append({**_label(e), "label": "OVERDUE", "days_overdue": -delta})
        elif delta in ALERT_OFFSETS:
            out.append({**_label(e), "label": ALERT_OFFSETS[delta], "days_to_due": delta})
    return out


def _label(e: dict) -> dict[str, Any]:
    return {"domain": e.get("domain"), "form_name": e.get("form_name"), "due_date": e["due_date"]}
