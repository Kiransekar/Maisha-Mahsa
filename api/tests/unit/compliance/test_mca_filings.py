"""MCA annual-filing deadlines — deferred feature."""

from __future__ import annotations

from app.domains.compliance.compliance_calc import mca_deadlines


def test_mca_deadlines_from_agm() -> None:
    forms = {f["form"]: f for f in mca_deadlines(agm_date="2026-09-30")}
    assert forms["AOC-4"]["due_date"] == "2026-10-30"  # AGM + 30 days
    assert forms["MGT-7"]["due_date"] == "2026-11-29"  # AGM + 60 days
    assert forms["DPT-3"]["due_date"] == "2026-06-30"
    assert forms["DIR-3 KYC"]["due_date"] == "2026-09-30"
    assert all(f["domain"] == "roc" and f["statute"] for f in forms.values())
