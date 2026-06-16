"""U4 emails — compliance alert, payroll approval, investor update (compose + render + send)."""

import pytest

from app.core.email.channel import EmailChannel
from app.core.email.compose import (
    compose_compliance_alert,
    compose_investor_update,
    compose_payroll_approval,
)
from app.core.email.renderer import render
from app.core.email.transport import InMemoryTransport
from app.core.money import Paise


# ---- compliance alert ----
def test_compose_and_render_compliance_alert():
    alerts = [
        {
            "domain": "gst",
            "form_name": "GSTR-3B (Apr)",
            "due_date": "2026-05-20",
            "label": "OVERDUE",
            "days_overdue": 27,
        },
        {"domain": "tds", "form_name": "TDS (May)", "due_date": "2026-06-23", "label": "T-7"},
    ]
    ctx = compose_compliance_alert(alerts, "2026-06-16")
    assert ctx["total"] == 2
    assert len(ctx["overdue"]) == 1 and len(ctx["upcoming"]) == 1
    html = render("compliance_alert.html", ctx=ctx)
    assert "GSTR-3B (Apr)" in html and "27 day(s) overdue" in html


# ---- payroll approval ----
def test_compose_and_render_payroll_approval():
    run = {
        "month_year": "2026-06",
        "employee_count": 1,
        "total_gross": Paise.from_rupees(100000),
        "total_deductions": Paise.from_rupees(2000),
        "total_net": Paise.from_rupees(98000),
        "total_pf_employer": Paise.from_rupees(1800),
        "total_esi_employer": 0,
    }
    entries = [
        {
            "name": "Asha",
            "gross": Paise.from_rupees(100000),
            "deductions": Paise.from_rupees(2000),
            "net": Paise.from_rupees(98000),
        }
    ]
    ctx = compose_payroll_approval(run, entries, validation_status="green", mahsa_note="ok")
    html = render("payroll_approval.html", ctx=ctx)
    assert "₹98,000.00" in html  # net via the rupees filter (Indian grouping)
    assert "Asha" in html and "GREEN" in html


# ---- investor update ----
def test_compose_and_render_investor_update():
    kpis = {
        "cash": Paise.from_rupees(12000000),
        "net_burn": Paise.from_rupees(200000),
        "runway_fmt": "60 mo",
        "ar": Paise.from_rupees(500000),
    }
    cap_table = {"total_shares": 1000000, "pct": {"founder": 0.7, "investor": 0.2, "esop": 0.1}}
    ctx = compose_investor_update("Q1 FY26-27", kpis, cap_table, highlights=["Closed seed round"])
    html = render("investor_update.html", ctx=ctx, company_name="Acme")
    assert "Q1 FY26-27" in html
    assert "70.0%" in html  # founder ownership
    assert "Closed seed round" in html


@pytest.mark.asyncio
async def test_channel_dispatches_all_u4_emails():
    transport = InMemoryTransport()
    channel = EmailChannel(transport)
    await channel.send_compliance_alert(
        to="f@x.test", ctx=compose_compliance_alert([], "2026-06-16")
    )
    run = {
        "month_year": "2026-06",
        "employee_count": 0,
        "total_gross": 0,
        "total_deductions": 0,
        "total_net": 0,
        "total_pf_employer": 0,
        "total_esi_employer": 0,
    }
    await channel.send_payroll_approval(
        to="f@x.test", ctx=compose_payroll_approval(run, [], validation_status="green")
    )
    await channel.send_investor_update(
        to="f@x.test",
        ctx=compose_investor_update("Q1", {}, {"total_shares": 0, "pct": {}}),
    )
    assert len(transport.sent) == 3
    assert "Compliance Alert" in transport.sent[0].subject
    assert "Payroll Approval" in transport.sent[1].subject
    assert "Investor Update" in transport.sent[2].subject
