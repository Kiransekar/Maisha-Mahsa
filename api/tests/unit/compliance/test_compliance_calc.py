"""Compliance-calendar logic checks — overdue count, per-statute health, alert cadence."""

from datetime import date

from app.domains.compliance import compliance_calc as c

_ENTRIES = [
    {"domain": "gst", "form_name": "GSTR-3B (Apr)", "due_date": "2026-05-20", "status": "pending"},
    {"domain": "tds", "form_name": "TDS (May)", "due_date": "2026-06-07", "status": "filed"},
    {"domain": "pf", "form_name": "PF (May)", "due_date": "2026-06-15", "status": "pending"},
    {"domain": "roc", "form_name": "AOC-4", "due_date": "2026-06-23", "status": "pending"},
]


def test_overdue_count_ignores_filed_and_future():
    # as_of 16 Jun: GSTR-3B (20 May) overdue; PF (15 Jun) overdue; TDS filed; ROC future
    assert c.overdue_count(_ENTRIES, date(2026, 6, 16)) == 2


def test_domain_health():
    health = c.domain_health(_ENTRIES, date(2026, 6, 16))
    assert health["gst"] == 0.0  # overdue
    assert health["pf"] == 0.0  # overdue
    assert health["tds"] == 1.0  # filed
    assert health["roc"] == 1.0  # not yet due
    assert health["esi"] == 1.0  # nothing on calendar


def test_alerts_cadence_and_overdue():
    alerts = c.alerts(_ENTRIES, date(2026, 6, 16))
    labels = {(a["domain"], a["label"]) for a in alerts}
    assert ("gst", "OVERDUE") in labels  # 20 May
    assert ("roc", "T-7") in labels  # 23 Jun is 7 days away
    # the filed TDS entry never alerts
    assert all(a["domain"] != "tds" for a in alerts)
