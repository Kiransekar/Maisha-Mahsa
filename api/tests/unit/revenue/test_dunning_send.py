"""Automated dunning reminder dispatch — deferred feature."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email.channel import EmailChannel
from app.core.email.compose import compose_dunning
from app.core.email.transport import InMemoryTransport
from app.core.money import Paise
from app.db.models.revenue import Customer, Invoice
from app.domains.revenue.service import RevenueService


def _customer(session: Session, *, email: str | None) -> int:
    c = Customer(name="Acme", state="MH", email=email, payment_terms=30)
    session.add(c)
    session.flush()
    return c.id


def _invoice(session: Session, svc: RevenueService, *, cust: int, num: str, due: str) -> None:
    svc.create_invoice(
        session,
        invoice_number=num,
        customer_id=cust,
        invoice_date="2026-05-01",
        lines=[
            {
                "description": "svc",
                "quantity": 1,
                "rate": Paise.from_rupees(100000),
                "hsn_code": "9983",
            }
        ],
        gst_rate=18,
    )
    # override the due date to drive the dunning schedule deterministically
    inv = session.scalars(select(Invoice).where(Invoice.invoice_number == num)).one()
    inv.due_date = due
    session.flush()


def test_compose_dunning_tone_and_overdue_flag() -> None:
    ctx = compose_dunning(
        {
            "invoice_number": "INV-1",
            "customer_name": "Acme",
            "outstanding": Paise.from_rupees(118000),
            "due_date": "2026-06-20",
            "stage": "T+7",
        },
        "2026-06-27",
    )
    assert ctx["overdue"] is True
    assert ctx["outstanding"] == Paise.from_rupees(118000)
    assert "overdue" in ctx["message"]


def test_pending_dunning_fires_on_schedule(session: Session) -> None:
    svc = RevenueService()
    cust = _customer(session, email="ap@acme.test")
    _invoice(session, svc, cust=cust, num="INV-1", due="2026-06-20")
    # as_of = due − 7 → the T-7 reminder fires
    pending = svc.pending_dunning(session, date(2026, 6, 13))
    assert len(pending) == 1
    assert pending[0]["stage"] == "T-7"
    assert pending[0]["customer_email"] == "ap@acme.test"


@pytest.mark.asyncio
async def test_dunning_run_dispatches_and_skips_no_email(session: Session) -> None:
    svc = RevenueService()
    with_email = _customer(session, email="ap@acme.test")
    no_email = _customer(session, email=None)
    _invoice(session, svc, cust=with_email, num="INV-1", due="2026-06-20")
    _invoice(session, svc, cust=no_email, num="INV-2", due="2026-06-20")

    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="ar@maisha.local")
    summary = await svc.dunning_run(session, date(2026, 6, 13), channel)  # T-7 for both

    assert summary["pending"] == 2
    assert summary["sent"] == 1
    assert summary["skipped_no_email"] == ["INV-2"]
    assert len(transport.sent) == 1
    assert transport.sent[0].to == "ap@acme.test"
    assert "INV-1" in transport.sent[0].subject


# ---- MEM.P1-2: dunning tone from the CFO posture block ------------------------------------

_ITEM = {
    "invoice_number": "INV-9",
    "customer_name": "Acme",
    "outstanding": 11_800_000,
    "due_date": "2026-06-20",
    "stage": "T+7",
}

_POSTURE = (
    "CFO POSTURE (durable preferences — context only, NEVER a source of numbers):\n"
    "- we value long-term customer relationships\n"
    "- Dunning tone: gentle\n"
)


def test_dunning_tone_directive_changes_closing_but_no_number() -> None:
    without = compose_dunning(dict(_ITEM), "2026-06-27")
    gentle = compose_dunning(dict(_ITEM), "2026-06-27", memory=_POSTURE)
    firm = compose_dunning(dict(_ITEM), "2026-06-27", memory="dunning tone: firm")

    assert without["tone"] == "standard"
    assert gentle["tone"] == "gentle" and "thank you" in gentle["closing"]
    assert firm["tone"] == "firm" and "further reminders" in firm["closing"]
    assert without["closing"] != gentle["closing"] != firm["closing"]
    # §0.4 firewall: every number and date is identical across tones.
    for key in ("outstanding", "due_date", "stage", "invoice_number", "overdue", "message"):
        assert without[key] == gentle[key] == firm[key]


def test_raw_posture_text_never_reaches_the_customer_context() -> None:
    """The memory block is DATA, not copy: no ctx value may carry the org's internal standing
    instructions into a customer-facing email."""
    ctx = compose_dunning(dict(_ITEM), "2026-06-27", memory=_POSTURE)
    for value in ctx.values():
        if isinstance(value, str):
            assert "CFO POSTURE" not in value
            assert "long-term customer relationships" not in value


def test_unrecognized_or_absent_directive_falls_back_to_standard() -> None:
    assert compose_dunning(dict(_ITEM), "2026-06-27", memory="dunning tone: rude")["tone"] == (
        "standard"
    )
    assert compose_dunning(dict(_ITEM), "2026-06-27", memory=None)["tone"] == "standard"


@pytest.mark.asyncio
async def test_dunning_run_threads_memory_into_the_rendered_email(session: Session) -> None:
    svc = RevenueService()
    cust = _customer(session, email="ap@acme.test")
    _invoice(session, svc, cust=cust, num="INV-1", due="2026-06-20")

    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="ar@maisha.local")
    await svc.dunning_run(session, date(2026, 6, 13), channel, memory=_POSTURE)

    [msg] = transport.sent
    assert "thank you" in msg.html  # the gentle closing rendered
    assert "CFO POSTURE" not in msg.html  # the block itself never leaks to the customer
