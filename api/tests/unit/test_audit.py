from dataclasses import replace

from app.core.audit import GENESIS_HASH, make_entry, verify_chain


def _payload(action: str) -> dict:
    return {
        "timestamp": "2026-06-16T20:00:00+00:00",
        "action": action,
        "domain": "treasury",
        "user_id": "founder",
        "query": None,
        "intent_global": [0.5] * 8,
        "intent_domain": None,
        "validation_status": "green",
        "rules_version": "2026.06.1",
    }


def _build_chain(n: int):
    entries = []
    prev = GENESIS_HASH
    for i in range(n):
        e = make_entry(prev, _payload(f"act-{i}"))
        entries.append(e)
        prev = e.this_hash
    return entries


def test_empty_chain_is_valid():
    assert verify_chain([]) is True


def test_intact_chain_verifies():
    assert verify_chain(_build_chain(5)) is True


def test_tampering_with_a_field_breaks_the_chain():
    chain = _build_chain(4)
    # mutate the validation_status of entry 1 without recomputing hashes
    chain[1] = replace(chain[1], validation_status="red")
    assert verify_chain(chain) is False


def test_reordering_breaks_the_chain():
    chain = _build_chain(3)
    chain[1], chain[2] = chain[2], chain[1]
    assert verify_chain(chain) is False
