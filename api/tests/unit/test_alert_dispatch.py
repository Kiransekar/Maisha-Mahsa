"""P5-ALERTS: the statutory-alert job dispatches compliance alerts due now (T-7/T-1/T-0)."""

from datetime import date

import pytest

from app.core.email.channel import EmailChannel
from app.core.email.transport import InMemoryTransport
from app.domains.compliance.service import ComplianceService
from app.jobs import run_alerts


@pytest.mark.asyncio
async def test_run_alerts_dispatches_due_deadline(session):
    # a deadline 7 days out -> a T-7 alert is due as of 2026-06-19
    ComplianceService().add_deadline(
        session, domain="gst", form_name="GSTR-3B", due_date="2026-06-26"
    )
    session.commit()

    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="cfo@x.local")
    result = await run_alerts(session, channel, to="founder@x.local", as_of=date(2026, 6, 19))

    assert result["dispatched"] >= 1
    assert len(transport.sent) == 1
    assert transport.sent[0].to == "founder@x.local"


@pytest.mark.asyncio
async def test_run_alerts_noop_when_nothing_due(session):
    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="cfo@x.local")
    result = await run_alerts(session, channel, to="founder@x.local", as_of=date(2026, 1, 1))
    assert result == {"job": "alerts", "dispatched": 0}
    assert transport.sent == []
