"""WS4.4 — per-tenant hash-chain conformance.

Each org owns an independent chain (its own genesis + head). Verifying one tenant validates
only that tenant and is blind to every other; tampering in one tenant is caught by that
tenant's verify and never touches another. Reuses the existing hash algorithm (no change to
``canonical_json``/``compute_hash``); the separation comes from a per-tenant genesis.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.audit import (
    GENESIS_HASH,
    compute_daily_root,
    edit_log_payload,
    make_entry,
    tenant_genesis,
    verify_chain,
)


def _payload(action: str, day: str = "2026-06-16") -> dict:
    return {
        "timestamp": f"{day}T20:00:00+00:00",
        "action": action,
        "domain": "ledger",
        "user_id": "founder",
        "query": None,
        "intent_global": None,
        "intent_domain": None,
        "validation_status": "green",
        "rules_version": "2026.06.1",
    }


def _chain(org: str, actions: list[str]) -> list:
    entries = []
    prev = tenant_genesis(org)
    for a in actions:
        e = make_entry(prev, _payload(a))
        entries.append(e)
        prev = e.this_hash
    return entries


# --- genesis-per-tenant -------------------------------------------------------------------


def test_genesis_is_distinct_per_tenant_and_not_the_global_genesis():
    ga, gb = tenant_genesis("org-a"), tenant_genesis("org-b")
    assert ga != gb
    assert ga != GENESIS_HASH and gb != GENESIS_HASH
    assert tenant_genesis("org-a") == ga  # deterministic


def test_empty_org_genesis_is_rejected():
    try:
        tenant_genesis("")
    except ValueError:
        return
    raise AssertionError("empty org must be rejected")


# --- independence (pure layer) ------------------------------------------------------------


def test_two_tenant_chains_are_independent():
    a = _chain("org-a", ["a0", "a1", "a2"])
    b = _chain("org-b", ["b0", "b1"])
    # Each verifies only against its OWN genesis.
    assert verify_chain(a, genesis=tenant_genesis("org-a")) is True
    assert verify_chain(b, genesis=tenant_genesis("org-b")) is True
    # A's chain does NOT validate against B's genesis (no cross-tenant replay).
    assert verify_chain(a, genesis=tenant_genesis("org-b")) is False
    # A's first entry never chains onto B's head → the two never interleave.
    assert a[0].prev_hash != b[-1].this_hash


def test_tamper_in_one_tenant_is_caught_there_and_does_not_touch_the_other():
    a = _chain("org-a", ["a0", "a1", "a2"])
    b = _chain("org-b", ["b0", "b1"])
    a[1] = replace(a[1], validation_status="red")  # forge a field without rehashing
    assert verify_chain(a, genesis=tenant_genesis("org-a")) is False  # detected in A
    assert verify_chain(b, genesis=tenant_genesis("org-b")) is True  # B untouched


# --- store layer: same table, reconstructed per tenant ------------------------------------


def test_store_append_and_verify_are_per_tenant(session: Session):
    audit_store.append_for(session, "org-a", _payload("a0"))
    audit_store.append_for(session, "org-b", _payload("b0"))
    audit_store.append_for(session, "org-a", _payload("a1"))

    assert len(audit_store.load_chain_for(session, "org-a")) == 2
    assert len(audit_store.load_chain_for(session, "org-b")) == 1
    assert audit_store.verify_chain_for(session, "org-a") is True
    assert audit_store.verify_chain_for(session, "org-b") is True
    # A tenant with no entries: empty chain, trivially valid.
    assert audit_store.load_chain_for(session, "org-c") == []
    assert audit_store.verify_chain_for(session, "org-c") is True


def test_store_tenant_heads_do_not_interleave(session: Session):
    # Interleaved writes must not chain A's entry onto B's head.
    e_a0 = audit_store.append_for(session, "org-a", _payload("a0"))
    audit_store.append_for(session, "org-b", _payload("b0"))
    e_a1 = audit_store.append_for(session, "org-a", _payload("a1"))
    assert e_a1.prev_hash == e_a0.this_hash  # A1 links to A0, not to B0


def test_store_tamper_detected_for_one_tenant_only(session: Session):
    audit_store.append_for(session, "org-a", _payload("a0"))
    audit_store.append_for(session, "org-a", _payload("a1"))
    audit_store.append_for(session, "org-b", _payload("b0"))
    session.flush()

    # Tamper with the first org-a row in place.
    from sqlalchemy import select

    from app.db.models.shared import AuditLog

    rows = session.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all()
    a_row = next(r for r in rows if r.action == "a0")
    a_row.validation_status = "red"
    session.flush()

    assert audit_store.verify_chain_for(session, "org-a") is False
    assert audit_store.verify_chain_for(session, "org-b") is True  # unaffected


# --- edit-log helper ----------------------------------------------------------------------


def test_edit_log_payload_is_a_sealable_non_pii_entry():
    p = edit_log_payload(
        timestamp="2026-06-16T20:00:00+00:00",
        domain="ledger",
        user_id="founder",
        record_type="journal_entry",
        record_id="JE-42",
        operation="update",
        rules_version="2026.06.1",
        before_hash="a" * 64,
        after_hash="b" * 64,
    )
    assert p["action"] == "record.update"
    # No record content leaked — only opaque keys + hashes in the descriptor.
    assert "JE-42" in p["query"] and "a" * 64 in p["query"]
    # It seals like any other entry, tamper-evident because query is inside core_payload.
    e = make_entry(tenant_genesis("org-a"), p)
    assert verify_chain([e], genesis=tenant_genesis("org-a")) is True
    tampered = replace(e, query=e.query.replace("update", "create") if e.query else "")
    assert verify_chain([tampered], genesis=tenant_genesis("org-a")) is False


def test_edit_log_rejects_bad_operation():
    try:
        edit_log_payload(
            timestamp="t",
            domain="ledger",
            user_id="u",
            record_type="x",
            record_id="1",
            operation="frobnicate",
            rules_version="rv",
        )
    except ValueError:
        return
    raise AssertionError("invalid operation must raise")


# --- daily root / anchoring ---------------------------------------------------------------


def test_daily_root_commits_to_the_days_entries_and_is_tamper_evident():
    a = _chain("org-a", ["a0", "a1"])
    r1 = compute_daily_root("org-a", "2026-06-16", a)
    assert r1.entry_count == 2 and r1.external_ref is None
    # Deterministic.
    assert compute_daily_root("org-a", "2026-06-16", a).root == r1.root
    # Any change to a sealed entry changes its this_hash → changes the root.
    a2 = _chain("org-a", ["a0", "a1-CHANGED"])
    assert compute_daily_root("org-a", "2026-06-16", a2).root != r1.root
    # Empty day still yields a stable, distinct root.
    assert compute_daily_root("org-a", "2026-06-17", []).root != r1.root


def test_store_daily_root_filters_by_org_and_day(session: Session):
    audit_store.append_for(session, "org-a", _payload("a0", day="2026-06-16"))
    audit_store.append_for(session, "org-a", _payload("a1", day="2026-06-17"))
    audit_store.append_for(session, "org-b", _payload("b0", day="2026-06-16"))

    anchor = audit_store.compute_daily_root_for(session, "org-a", "2026-06-16")
    assert anchor.org == "org-a" and anchor.day == "2026-06-16"
    assert anchor.entry_count == 1  # only org-a's 06-16 entry, not org-b's, not 06-17
