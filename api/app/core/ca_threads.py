"""WS8.2 — CA query threads pinned to entries, plus the deterministic audit-sampling helper.

A thread is pinned to a ledger entry / figure reference (``domain`` + ``entry_ref``) and moves
open -> responded -> resolved. EVERY transition appends a ``ca_thread.*`` event onto the
EXISTING hash-chained audit log via :func:`app.core.audit_store.append` — the same
``AuditEntry`` core shape every other event uses, so history is extended, never mutated, and
``verify_chain`` covers thread events for free. Like :func:`app.core.audit.edit_log_payload`,
the sealed descriptor carries opaque refs and a note *hash*, never the note text (§0.8 no PII
in the chain); the raw text lives in ``ca_thread_event``, the queryable mirror.

Sampling: given a selection spec (domain, date range, n) the sample is DETERMINISTIC — seeded
by sha256(org + canonical spec), each candidate voucher ranked by sha256(seed + voucher id),
n smallest win. No RNG anywhere (determinism rule): same org + same spec = same sample,
re-runnable by the CA and by us in a dispute, forever.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.audit import canonical_json
from app.db.models.ledger import JournalEntry
from app.db.models.shared import CaThread, CaThreadEvent
from app.db.models.vault import Document

RULES_VERSION = "ca_threads.2026.1"


def thread_event_payload(
    *,
    timestamp: str,
    domain: str,
    user_id: str,
    thread_id: int,
    entry_ref: str,
    event: str,
    doc_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Audit payload for one thread event — ``AuditEntry`` core shape, chained by the caller.

    The descriptor is inside the hashed ``query`` field, so which thread, which entry, which
    vault doc and which note (by sha256) are all tamper-evident. Raw note text never enters
    the chain (mirrors :func:`app.core.audit.edit_log_payload`'s no-content stance)."""
    if event not in ("raise", "respond", "resolve"):
        raise ValueError(f"event must be raise/respond/resolve, got {event!r}")
    descriptor = canonical_json(
        {
            "thread": thread_id,
            "entry": entry_ref,
            "event": event,
            "doc": doc_id,
            "note_sha256": hashlib.sha256(note.encode("utf-8")).hexdigest() if note else None,
        }
    )
    return {
        "timestamp": timestamp,
        "action": f"ca_thread.{event}",
        "domain": domain,
        "user_id": user_id,
        "query": descriptor,
        "intent_global": None,
        "intent_domain": None,
        "validation_status": "recorded",
        "rules_version": RULES_VERSION,
    }


def _seal_event(
    session: Session,
    thread: CaThread,
    *,
    timestamp: str,
    event: str,
    user_id: str,
    note: str | None,
    doc_id: str | None,
) -> CaThreadEvent:
    """Append the event row AND its audit entry; the row records the sealed hash."""
    entry = audit_store.append(
        session,
        thread_event_payload(
            timestamp=timestamp,
            domain=thread.domain,
            user_id=user_id,
            thread_id=thread.id,
            entry_ref=thread.entry_ref,
            event=event,
            doc_id=doc_id,
            note=note,
        ),
    )
    row = CaThreadEvent(
        thread_id=thread.id,
        timestamp=timestamp,
        event=event,
        user_id=user_id,
        note=note,
        doc_id=doc_id,
        audit_hash=entry.this_hash,
    )
    session.add(row)
    session.flush()
    return row


def raise_thread(
    session: Session,
    *,
    timestamp: str,
    domain: str,
    entry_ref: str,
    question: str,
    user_id: str,
) -> CaThread:
    """CA raises a query pinned to ``entry_ref`` in ``domain``. State: open."""
    if not entry_ref.strip() or not question.strip():
        raise ValueError("entry_ref and question must be non-empty")
    thread = CaThread(
        created_at=timestamp,
        domain=domain,
        entry_ref=entry_ref,
        question=question,
        state="open",
        raised_by=user_id,
    )
    session.add(thread)
    session.flush()
    _seal_event(
        session, thread, timestamp=timestamp, event="raise", user_id=user_id,
        note=question, doc_id=None,
    )
    return thread


def _get_thread(session: Session, thread_id: int) -> CaThread:
    thread = session.get(CaThread, thread_id)
    if thread is None:
        raise LookupError(f"unknown thread {thread_id}")
    return thread


def respond_thread(
    session: Session,
    *,
    thread_id: int,
    timestamp: str,
    note: str,
    doc_id: str,
    user_id: str,
) -> CaThread:
    """Accountant/Owner responds WITH a vault document. open|responded -> responded.

    ``doc_id`` must name an existing vault document — a respond that points at nothing is
    refused, not recorded (the whole point of respond-with-doc is an evidence link)."""
    thread = _get_thread(session, thread_id)
    if thread.state == "resolved":
        raise ValueError(f"thread {thread_id} is resolved; nothing to respond to")
    if session.get(Document, doc_id) is None:
        raise LookupError(f"unknown vault document {doc_id!r}")
    thread.state = "responded"
    _seal_event(
        session, thread, timestamp=timestamp, event="respond", user_id=user_id,
        note=note, doc_id=doc_id,
    )
    return thread


def resolve_thread(
    session: Session,
    *,
    thread_id: int,
    timestamp: str,
    note: str,
    user_id: str,
) -> CaThread:
    """CA closes the query. Only a *responded* thread can resolve — resolving an unanswered
    query would erase the fact that it was never answered."""
    thread = _get_thread(session, thread_id)
    if thread.state != "responded":
        raise ValueError(
            f"thread {thread_id} is {thread.state}; only a responded thread can be resolved"
        )
    thread.state = "resolved"
    _seal_event(
        session, thread, timestamp=timestamp, event="resolve", user_id=user_id,
        note=note, doc_id=None,
    )
    return thread


def list_threads(session: Session) -> list[CaThread]:
    """All threads, newest first."""
    return list(session.scalars(select(CaThread).order_by(CaThread.id.desc())).all())


def events_for(session: Session, thread_id: int) -> list[CaThreadEvent]:
    """A thread's events in seal order."""
    return list(
        session.scalars(
            select(CaThreadEvent)
            .where(CaThreadEvent.thread_id == thread_id)
            .order_by(CaThreadEvent.id.asc())
        ).all()
    )


# --- deterministic sampling -----------------------------------------------------------------


def sample_selection(
    session: Session,
    *,
    org: str,
    domain: str | None,
    date_from: str,
    date_to: str,
    n: int,
) -> dict[str, Any]:
    """Deterministic voucher sample for a CA selection spec — NO RNG.

    Population: journal entries with ``entry_date`` in [date_from, date_to] (ISO strings sort
    correctly), filtered to ``source == domain`` when a domain is given. Each candidate is
    ranked by ``sha256(seed + ":" + id)`` where ``seed = sha256(org + "|" + canonical(spec))``;
    the ``n`` smallest ranks are the sample, returned in voucher-id order with each voucher's
    linked vault doc bundle (documents whose ``entity_id`` names the voucher id or its
    human reference)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    spec = {"domain": domain, "date_from": date_from, "date_to": date_to, "n": n}
    seed = hashlib.sha256(f"{org}|{canonical_json(spec)}".encode()).hexdigest()

    q = select(JournalEntry).where(
        JournalEntry.entry_date >= date_from, JournalEntry.entry_date <= date_to
    )
    if domain:
        q = q.where(JournalEntry.source == domain)
    population = session.scalars(q).all()

    def _rank(e: JournalEntry) -> str:
        return hashlib.sha256(f"{seed}:{e.id}".encode()).hexdigest()

    chosen = sorted(sorted(population, key=_rank)[:n], key=lambda e: e.id)

    vouchers: list[dict[str, Any]] = []
    for e in chosen:
        keys = {str(e.id)} | ({e.reference} if e.reference else set())
        docs = session.scalars(
            select(Document).where(Document.entity_id.in_(sorted(keys)))
        ).all()
        vouchers.append(
            {
                "voucher_id": e.id,
                "entry_date": e.entry_date,
                "reference": e.reference,
                "description": e.description,
                "source": e.source,
                "total_debit_paise": e.total_debit,
                "total_credit_paise": e.total_credit,
                "documents": [
                    {"doc_id": d.id, "file_name": d.file_name, "doc_type": d.doc_type}
                    for d in docs
                ],
            }
        )
    return {"spec": spec, "seed": seed, "population": len(population), "sample": vouchers}
