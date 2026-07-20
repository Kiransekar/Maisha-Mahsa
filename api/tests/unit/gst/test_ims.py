"""IMS inward-invoice state machine — accept/reject/pending → ITC eligibility."""

from __future__ import annotations

from datetime import date

from app.core.money import Paise
from app.domains.gst.ims import InwardInvoice, ims_disposition

_DEADLINE = date(2026, 8, 20)
_BEFORE = date(2026, 8, 10)
_AFTER = date(2026, 8, 21)


def test_accept_is_itc_eligible() -> None:
    inv = InwardInvoice(
        id="INV1", itc_paise=Paise.from_rupees(1000), deadline=_DEADLINE, action="accept"
    )
    res = ims_disposition([inv], as_of=_BEFORE)
    row = res["invoices"][0]
    assert row["state"] == "accepted"
    assert row["itc_eligible"] is True


def test_reject_is_not_itc_eligible() -> None:
    inv = InwardInvoice(
        id="INV2", itc_paise=Paise.from_rupees(1000), deadline=_DEADLINE, action="reject"
    )
    res = ims_disposition([inv], as_of=_BEFORE)
    row = res["invoices"][0]
    assert row["state"] == "rejected"
    assert row["itc_eligible"] is False


def test_pending_before_deadline_stays_pending_and_ineligible() -> None:
    inv = InwardInvoice(
        id="INV3", itc_paise=Paise.from_rupees(1000), deadline=_DEADLINE, action=None
    )
    res = ims_disposition([inv], as_of=_BEFORE)
    row = res["invoices"][0]
    assert row["state"] == "pending"
    assert row["itc_eligible"] is False


def test_pending_past_deadline_is_deemed_accepted() -> None:
    inv = InwardInvoice(
        id="INV4", itc_paise=Paise.from_rupees(1000), deadline=_DEADLINE, action=None
    )
    res = ims_disposition([inv], as_of=_AFTER)
    row = res["invoices"][0]
    assert row["state"] == "deemed_accepted"
    assert row["itc_eligible"] is True


def test_pending_on_deadline_day_is_deemed_accepted() -> None:
    # deadline itself is inclusive (as_of >= deadline)
    inv = InwardInvoice(
        id="INV5", itc_paise=Paise.from_rupees(1000), deadline=_DEADLINE, action=None
    )
    res = ims_disposition([inv], as_of=_DEADLINE)
    row = res["invoices"][0]
    assert row["state"] == "deemed_accepted"
    assert row["itc_eligible"] is True


def test_aggregate_sums_only_accepted_and_deemed_rows() -> None:
    invoices = [
        InwardInvoice(
            id="ACC", itc_paise=Paise.from_rupees(10000), deadline=_DEADLINE, action="accept"
        ),
        InwardInvoice(
            id="DEEMED", itc_paise=Paise.from_rupees(5000), deadline=_DEADLINE, action=None
        ),
        InwardInvoice(
            id="STILL_PENDING", itc_paise=Paise.from_rupees(7000), deadline=_DEADLINE, action=None
        ),
        InwardInvoice(
            id="REJECTED_HIGH",
            itc_paise=Paise.from_rupees(999999),
            deadline=_DEADLINE,
            action="reject",
        ),
    ]
    res = ims_disposition(invoices, as_of=_AFTER)
    # DEEMED and STILL_PENDING both resolve past the deadline → both deemed-accepted.
    assert res["eligible_itc_total_paise"] == Paise.from_rupees(10000) + Paise.from_rupees(
        5000
    ) + Paise.from_rupees(7000)
    # the high-value rejected invoice must never enter the eligible total
    assert res["eligible_itc_total_paise"] < Paise.from_rupees(999999)


def test_rejected_high_value_excluded_even_when_others_pending() -> None:
    invoices = [
        InwardInvoice(
            id="REJ", itc_paise=Paise.from_rupees(500000), deadline=_DEADLINE, action="reject"
        ),
        InwardInvoice(
            id="PENDING", itc_paise=Paise.from_rupees(100), deadline=_DEADLINE, action=None
        ),
    ]
    res = ims_disposition(invoices, as_of=_BEFORE)  # before deadline: pending stays pending
    assert res["eligible_itc_total_paise"] == 0
    states = {row["id"]: row["state"] for row in res["invoices"]}
    assert states["REJ"] == "rejected"
    assert states["PENDING"] == "pending"
