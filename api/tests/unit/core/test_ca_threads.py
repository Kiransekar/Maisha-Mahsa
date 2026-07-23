"""WS8.2 — CA query threads: lifecycle chained into the audit log, and deterministic sampling."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.ca_threads import (
    raise_thread,
    resolve_thread,
    respond_thread,
    sample_selection,
)
from app.db.models.ledger import JournalEntry
from app.db.models.shared import AuditLog, CaThreadEvent
from app.db.models.vault import Document

TS = "2026-07-22T10:00:00+00:00"


def _doc(session, doc_id: str = "a" * 64, entity_id: str | None = None) -> Document:
    doc = Document(
        id=doc_id,
        file_name="invoice.pdf",
        file_path="/vault/invoice.pdf",
        doc_type="invoice",
        entity_id=entity_id,
        upload_date="2026-07-01",
        sha256=doc_id,
    )
    session.add(doc)
    session.flush()
    return doc


# --- lifecycle ------------------------------------------------------------------------------


def test_full_lifecycle_chains_every_event_into_the_verifiable_audit_log(session):
    doc = _doc(session)
    thread = raise_thread(
        session,
        timestamp=TS,
        domain="ledger",
        entry_ref="journal:42",
        question="Why is this debit unsupported?",
        user_id="ca-1",
    )
    assert thread.state == "open"

    respond_thread(
        session,
        thread_id=thread.id,
        timestamp=TS,
        note="invoice attached",
        doc_id=doc.id,
        user_id="acct-1",
    )
    assert thread.state == "responded"

    resolve_thread(session, thread_id=thread.id, timestamp=TS, note="satisfied", user_id="ca-1")
    assert thread.state == "resolved"

    chain = load_chain(session)
    assert [e.action for e in chain] == [
        "ca_thread.raise",
        "ca_thread.respond",
        "ca_thread.resolve",
    ]
    assert verify_chain(chain), "thread events must extend the REAL hash chain"
    assert [e.user_id for e in chain] == ["ca-1", "acct-1", "ca-1"]

    # The sealed respond descriptor is tamper-evident: thread, entry, doc, and the note by
    # sha256 — the raw note text itself never enters the chain (no PII, §0.8).
    respond_entry = chain[1]
    assert respond_entry.query is not None
    assert f'"thread":{thread.id}' in respond_entry.query
    assert "journal:42" in respond_entry.query
    assert doc.id in respond_entry.query
    assert "invoice attached" not in respond_entry.query
    assert hashlib.sha256(b"invoice attached").hexdigest() in respond_entry.query

    # Each mirror event row records the hash of ITS sealed chain entry.
    events = session.scalars(select(CaThreadEvent).order_by(CaThreadEvent.id)).all()
    assert [ev.event for ev in events] == ["raise", "respond", "resolve"]
    assert [ev.audit_hash for ev in events] == [e.this_hash for e in chain]
    assert events[1].note == "invoice attached"  # raw text lives in the mirror only

    # Tampering with any sealed event breaks verification — never silently repaired.
    row = session.scalars(select(AuditLog).order_by(AuditLog.id)).all()[1]
    row.query = row.query.replace(doc.id, "b" * 64)
    session.flush()
    assert not verify_chain(load_chain(session))


def test_transitions_and_doc_link_are_enforced_and_refusals_seal_nothing(session):
    doc = _doc(session)
    thread = raise_thread(
        session,
        timestamp=TS,
        domain="gst",
        entry_ref="journal:7",
        question="Support for this ITC claim?",
        user_id="ca-1",
    )

    # An open thread cannot resolve — that would erase "never answered".
    with pytest.raises(ValueError, match="only a responded thread"):
        resolve_thread(session, thread_id=thread.id, timestamp=TS, note="", user_id="ca-1")

    # respond-with-doc must point at a REAL vault document.
    with pytest.raises(LookupError, match="unknown vault document"):
        respond_thread(
            session,
            thread_id=thread.id,
            timestamp=TS,
            note="x",
            doc_id="f" * 64,
            user_id="acct-1",
        )
    # unknown thread ids are refused too
    with pytest.raises(LookupError, match="unknown thread"):
        respond_thread(
            session, thread_id=999, timestamp=TS, note="x", doc_id=doc.id, user_id="acct-1"
        )

    assert thread.state == "open"
    assert [e.action for e in load_chain(session)] == ["ca_thread.raise"], (
        "a refused transition must seal NO audit event"
    )

    respond_thread(
        session,
        thread_id=thread.id,
        timestamp=TS,
        note="here",
        doc_id=doc.id,
        user_id="acct-1",
    )
    resolve_thread(session, thread_id=thread.id, timestamp=TS, note="", user_id="ca-1")
    with pytest.raises(ValueError, match="resolved"):
        respond_thread(
            session,
            thread_id=thread.id,
            timestamp=TS,
            note="late",
            doc_id=doc.id,
            user_id="acct-1",
        )


def test_raise_rejects_empty_pin_or_question(session):
    with pytest.raises(ValueError):
        raise_thread(
            session,
            timestamp=TS,
            domain="ledger",
            entry_ref="  ",
            question="q",
            user_id="ca-1",
        )
    with pytest.raises(ValueError):
        raise_thread(
            session,
            timestamp=TS,
            domain="ledger",
            entry_ref="journal:1",
            question=" ",
            user_id="ca-1",
        )
    assert load_chain(session) == []


# --- deterministic sampling -----------------------------------------------------------------


def _seed_vouchers(session, count: int, source: str = "gst") -> list[JournalEntry]:
    rows = []
    for i in range(count):
        e = JournalEntry(
            entry_date=f"2026-07-{i + 1:02d}",
            reference=f"V-{source}-{i + 1}",
            description=f"{source} voucher {i + 1}",
            source=source,
            total_debit=100_00 + i,
            total_credit=100_00 + i,
        )
        session.add(e)
        rows.append(e)
    session.flush()
    return rows


def test_sample_is_deterministic_and_seeded_by_org_and_spec(session):
    gst = _seed_vouchers(session, 12, "gst")
    _seed_vouchers(session, 3, "payroll")
    _doc(session, doc_id="c" * 64, entity_id=gst[2].reference)  # pinned by human reference
    _doc(session, doc_id="d" * 64, entity_id=str(gst[5].id))  # pinned by voucher id

    kwargs = dict(domain="gst", date_from="2026-07-01", date_to="2026-07-31", n=5)
    s1 = sample_selection(session, org="org-7", **kwargs)
    s2 = sample_selection(session, org="org-7", **kwargs)
    assert s1 == s2, "same org + same spec must reproduce the sample EXACTLY"
    assert len(s1["sample"]) == 5
    assert s1["population"] == 12

    # The ranking is the documented contract — sha256(seed + ":" + id), n smallest —
    # recomputed here independently, so a swap to RNG or first-n-by-id fails this test.
    seed = s1["seed"]
    expected = sorted(
        (e.id for e in gst),
        key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest(),
    )[:5]
    assert [v["voucher_id"] for v in s1["sample"]] == sorted(expected)

    # Seeded by org: a different org draws a different sample from the same population.
    s_other = sample_selection(session, org="org-8", **kwargs)
    assert {v["voucher_id"] for v in s_other["sample"]} != {v["voucher_id"] for v in s1["sample"]}

    # Spec is part of the seed: same n, shifted window, different draw order.
    filters_hold = sample_selection(
        session,
        org="org-7",
        domain="payroll",
        date_from="2026-07-01",
        date_to="2026-07-31",
        n=5,
    )
    assert filters_hold["population"] == 3
    assert len(filters_hold["sample"]) == 3  # n capped by population, all returned
    assert all(v["source"] == "payroll" for v in filters_hold["sample"])

    # Date range filter is honoured.
    windowed = sample_selection(
        session,
        org="org-7",
        domain="gst",
        date_from="2026-07-01",
        date_to="2026-07-04",
        n=10,
    )
    assert windowed["population"] == 4
    assert all(v["entry_date"] <= "2026-07-04" for v in windowed["sample"])

    # Linked vault doc bundle: whichever pinned voucher is drawn carries its doc ref.
    by_id = {v["voucher_id"]: v for v in s1["sample"]}
    if gst[2].id in by_id:
        assert [d["doc_id"] for d in by_id[gst[2].id]["documents"]] == ["c" * 64]
    if gst[5].id in by_id:
        assert [d["doc_id"] for d in by_id[gst[5].id]["documents"]] == ["d" * 64]
    # ...and the pinned-by-reference bundle is proven directly with n = population:
    everything = sample_selection(
        session,
        org="org-7",
        domain="gst",
        date_from="2026-07-01",
        date_to="2026-07-31",
        n=12,
    )
    all_by_id = {v["voucher_id"]: v for v in everything["sample"]}
    assert [d["doc_id"] for d in all_by_id[gst[2].id]["documents"]] == ["c" * 64]
    assert [d["doc_id"] for d in all_by_id[gst[5].id]["documents"]] == ["d" * 64]
    assert all_by_id[gst[0].id]["documents"] == []


def test_sample_rejects_nonpositive_n(session):
    with pytest.raises(ValueError):
        sample_selection(
            session,
            org="org-7",
            domain=None,
            date_from="2026-07-01",
            date_to="2026-07-31",
            n=0,
        )
