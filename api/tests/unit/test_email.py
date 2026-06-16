"""Email rendering + channel dispatch (via the in-memory transport — no SMTP)."""

import pytest

from app.core.cfo import DomainHealth, compose_brief
from app.core.email.channel import EmailChannel
from app.core.email.renderer import render_daily_brief
from app.core.email.transport import InMemoryTransport


def _brief():
    return compose_brief(
        "2026-06-16",
        [
            DomainHealth("treasury", 92.0, "green", False),
            DomainHealth(
                "gst",
                40.0,
                "red",
                True,
                [{"text": "GSTR-3B late", "citation": "CGST Act — s.47", "action": "File now"}],
            ),
        ],
    )


def test_render_daily_brief_contains_scorecard_and_banner():
    html = render_daily_brief(_brief(), company_name="Acme")
    assert "Daily CFO Brief" in html
    assert "treasury" in html and "gst" in html
    assert "GSTR-3B late" in html  # banner from the red domain
    assert "CGST Act — s.47" in html  # citation rendered
    assert "92" in html  # treasury score


@pytest.mark.asyncio
async def test_email_channel_dispatches_via_transport():
    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="cfo@acme.test")
    await channel.send_daily_brief(to="founder@acme.test", brief=_brief(), company_name="Acme")

    assert len(transport.sent) == 1
    msg = transport.sent[0]
    assert msg.to == "founder@acme.test"
    assert "Daily CFO Brief" in msg.subject
    assert "1 need(s) attention" in msg.subject  # one red domain
    assert "<html" in msg.html.lower()
