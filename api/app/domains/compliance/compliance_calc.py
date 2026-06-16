"""Compliance-calendar logic — pure, deterministic. Operates on plain entry dicts
({domain, form_name, due_date, status}) so it is trivially testable. Time is injected
via ``as_of``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Statutory domains that map 1:1 onto the compliance sub-vector dimensions.
STATUTORY_DOMAINS = ("roc", "gst", "tds", "pf", "esi", "pt")

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
