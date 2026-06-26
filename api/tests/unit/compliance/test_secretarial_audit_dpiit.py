"""Compliance: secretarial calendar, audit-support package, DPIIT eligibility
(features secretarial / audit_support / dpiit)."""

from app.core.money import Paise
from app.domains.compliance import compliance_calc as c


def test_board_meeting_compliance():
    # 4 meetings, all within 120 days -> compliant
    ok = c.board_meeting_compliance(["2026-01-15", "2026-04-10", "2026-07-05", "2026-09-30"])
    assert ok["compliant"] is True and ok["meetings"] == 4
    # only 2 meetings, gap > 120 days -> not compliant, two reasons
    bad = c.board_meeting_compliance(["2026-01-01", "2026-08-01"])
    assert bad["compliant"] is False
    assert bad["max_gap_days"] > 120


def test_secretarial_calendar_has_agm_within_six_months():
    cal = c.secretarial_calendar("2026-03-31")
    agm = next(i for i in cal if i["item"] == "Annual General Meeting")
    assert agm["due_date"] == "2026-09-30"  # FY end + 6 months
    assert sum(1 for i in cal if i["item"].startswith("Board meeting")) == 4


def test_audit_support_package_readiness():
    pkg = c.audit_support_package({"trial_balance", "general_ledger", "bank_statements"})
    assert "fixed_asset_register" in pkg["missing"]
    assert 0 < pkg["readiness_pct"] < 100
    full = c.audit_support_package(set(c.AUDIT_CHECKLIST))
    assert full["readiness_pct"] == 100.0 and full["missing"] == []


def test_dpiit_eligibility():
    ok = c.dpiit_eligibility(
        incorporation_date="2022-06-01", as_of="2026-06-26",
        annual_turnover_paise=Paise.from_rupees(50_000_000),
    )
    assert ok["eligible"] is True and ok["reasons"] == []
    # too old + reconstituted -> ineligible
    bad = c.dpiit_eligibility(
        incorporation_date="2010-01-01", as_of="2026-06-26",
        annual_turnover_paise=Paise.from_rupees(50_000_000), is_reconstituted=True,
    )
    assert bad["eligible"] is False and len(bad["reasons"]) == 2
    # turnover >= 100 crore -> ineligible
    big = c.dpiit_eligibility(
        incorporation_date="2023-01-01", as_of="2026-06-26",
        annual_turnover_paise=Paise.from_rupees(100_00_00_000),
    )
    assert big["eligible"] is False
