"""F6 audit/trace viewer backend: trace reader + chain load/verify feed the /audit page."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import audit_store, trace_store
from app.core.audit import verify_chain
from app.llm.schema import ActionClaim


def test_trace_recent_newest_first(session: Session) -> None:
    for i in range(3):
        trace_store.append(
            session, timestamp=f"t{i}", domain="gst", audit_hash=None,
            model_label="ollama:qwen3:14b", input_sha256="a" * 64,
            claim=ActionClaim(domain="gst", claims={"x": str(i)}),
            attempts=1, verified=True, requires_approval=False, latency_ms=12,
        )
    rows = trace_store.recent(session, limit=2)
    assert len(rows) == 2
    assert rows[0].timestamp == "t2"  # newest first


def test_chain_loads_and_verifies(session: Session) -> None:
    assert verify_chain(load_chain := audit_store.load_chain(session)) is True  # empty = valid
    assert load_chain == []
    audit_store.append(session, {
        "timestamp": "t", "action": "fold", "domain": "gst", "user_id": "founder",
        "query": None, "intent_global": None, "intent_domain": None,
        "validation_status": "green", "rules_version": "rv",
    })
    chain = audit_store.load_chain(session)
    assert len(chain) == 1
    assert verify_chain(chain) is True
