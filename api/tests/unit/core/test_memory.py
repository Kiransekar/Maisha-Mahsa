"""SPEC-MEMCITE-1.0 MEM.P0-1/P0-2 — memory service: consolidation, reject-on-overflow,
archive-on-supersede + memory.update seal, history trail, Principal-only org scoping, and the
playbook-feedback ₹800→₹0 case (verified live in api-nest, ported here).

Mutation-proofing notes: the overflow test asserts NOTHING was written (row, history, chain);
the seal test asserts hashes-only in the sealed query; the ₹-case pins exact paise values and
the s.47 cap, so a naive ``days * 50_00`` reimplementation (dropping the statutory cap) fails.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.core import memory
from app.core.audit_store import load_chain_for, verify_chain_for
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.memory import OrgMemory, OrgMemoryHistory, PlaybookFeedback
from app.db.models.shared import AuditLog

ORG_A = Principal(user_id="user-a", org_id="org-a", role=Role.OWNER, email="a@example.com")
ORG_B = Principal(user_id="user-b", org_id="org-b", role=Role.OWNER, email="b@example.com")

NOW = "2026-07-23T12:00:00+00:00"


# ---- consolidate: deterministic, LLM-free ------------------------------------------------


def test_consolidate_dedupes_case_insensitively_ignoring_bullets():
    src = "- Prefer old regime\nprefer OLD regime\n\n* Prefer old regime\n- Quarterly reviews"
    assert memory.consolidate(src) == "- Prefer old regime\n- Quarterly reviews"


def test_consolidate_trims_and_drops_empty_lines():
    assert memory.consolidate("  a  \n\n   \n b ") == "a\nb"


# ---- set/get: cap, reject-on-overflow, seal ----------------------------------------------


def test_set_and_get_roundtrip_with_budget(session):
    out = memory.set_cfo(session, ORG_A, "- Conservative risk appetite", now=NOW)
    assert out["content"] == "- Conservative risk appetite"
    assert out["used"] == len(out["content"])
    assert out["limit"] == 2200
    got = memory.get_cfo(session, ORG_A)
    assert got["content"] == "- Conservative risk appetite"


def test_overflow_is_rejected_never_truncated_and_writes_nothing(session):
    # Unique lines so consolidation cannot rescue it: > 2200 chars survive.
    big = "\n".join(f"- durable fact number {i:04d} about the company posture" for i in range(60))
    assert len(memory.consolidate(big)) > 2200
    with pytest.raises(memory.MemoryOverflow) as exc:
        memory.set_cfo(session, ORG_A, big, now=NOW)
    assert "the limit is 2200" in str(exc.value)
    # NOTHING was written: no block, no history, no audit event (reject, not truncate).
    assert session.scalars(select(OrgMemory)).all() == []
    assert session.scalars(select(OrgMemoryHistory)).all() == []
    assert load_chain_for(session, ORG_A.org_id) == []


def test_write_is_sealed_hashes_only_and_chain_verifies(session):
    content = "- Never auto-file; always ask"
    memory.set_cfo(session, ORG_A, content, now=NOW)
    chain = load_chain_for(session, ORG_A.org_id)
    assert [e.action for e in chain] == ["memory.update"]
    assert chain[0].user_id == "user-a"
    assert chain[0].rules_version == "memory/v1"
    assert verify_chain_for(session, ORG_A.org_id)
    # hashes only in the sealed query — never the memory content itself
    digest = hashlib.sha256(content.encode()).hexdigest()
    assert digest in (chain[0].query or "")
    assert content not in (chain[0].query or "")


def test_noop_set_seals_nothing_and_archives_nothing(session):
    memory.set_cfo(session, ORG_A, "- Same content", now=NOW)
    memory.set_cfo(session, ORG_A, "- Same content", now=NOW)
    assert len(load_chain_for(session, ORG_A.org_id)) == 1
    assert memory.get_history(session, ORG_A) == []


# ---- archive-on-supersede + history trail ------------------------------------------------


def test_supersede_archives_prior_version_linked_to_the_sealed_event(session):
    memory.set_cfo(session, ORG_A, "- v1", now=NOW)
    memory.set_cfo(session, ORG_A, "- v2", now=NOW)
    memory.set_cfo(session, ORG_A, "- v3", now=NOW)

    trail = memory.get_history(session, ORG_A)
    assert [h["content"] for h in trail] == ["- v2", "- v1"]  # newest first
    assert all(h["superseded_by"] == "user-a" for h in trail)
    # audit_seq points at a REAL sealed memory.update row (§7.7 auditable updates)
    for h in trail:
        assert h["audit_seq"] is not None
        row = session.get(AuditLog, h["audit_seq"])
        assert row is not None and row.action == "memory.update"
    # the active block was replaced, never duplicated
    rows = session.scalars(select(OrgMemory)).all()
    assert len(rows) == 1 and rows[0].content == "- v3"


def test_append_builds_a_bullet_line_and_dedupes_via_consolidation(session):
    memory.append_cfo(session, ORG_A, "Prefer quarterly investor updates", now=NOW)
    out = memory.append_cfo(session, ORG_A, "Prefer quarterly investor updates", now=NOW)
    assert out["content"] == "- Prefer quarterly investor updates"  # once, not twice
    assert len(load_chain_for(session, ORG_A.org_id)) == 1  # the duplicate append sealed nothing


def test_append_overflow_leaves_stored_block_untouched(session):
    memory.set_cfo(session, ORG_A, "- keep me", now=NOW)
    with pytest.raises(memory.MemoryOverflow):
        memory.append_cfo(session, ORG_A, "x" * 3000, now=NOW)
    assert memory.get_cfo(session, ORG_A)["content"] == "- keep me"


# ---- Principal-only org scoping (§A3) ----------------------------------------------------


def test_cross_org_service_reads_are_empty(session):
    memory.set_cfo(session, ORG_A, "- org A secret posture", now=NOW)
    memory.record_feedback(session, ORG_A, memory.GST_LATEFEE, "dismissed", now=NOW)

    assert memory.get_cfo(session, ORG_B)["content"] == ""
    assert memory.get_history(session, ORG_B) == []
    assert "org A secret posture" not in memory.profile_text(session, ORG_B)
    # org A's dismissal must not zero org B's quantified savings
    b_moves = memory.playbook_moves(session, ORG_B, {"gstr3b_days_late": 16})
    assert b_moves["quantified_saving_paise"] == 80_000


# ---- playbook feedback: the ₹800 → ₹0 case (api-nest c0b075f, ported) --------------------


def test_dismissing_gst_latefee_flips_quantified_savings_800_to_0(session):
    facts = {"gstr3b_days_late": 16}
    before = memory.playbook_moves(session, ORG_A, facts)
    # 16 days × ₹50/day (gst_calc.late_fee_3b, s.47) = ₹800 = 80_000 paise
    assert before["quantified_saving_paise"] == 80_000
    assert before["moves"][0]["id"] == memory.GST_LATEFEE
    assert before["moves"][0]["feedback"] is None

    memory.record_feedback(session, ORG_A, memory.GST_LATEFEE, "dismissed", now=NOW)
    after = memory.playbook_moves(session, ORG_A, facts)
    assert after["quantified_saving_paise"] == 0  # ₹800 → ₹0
    # the move stays LISTED (honesty) — only the quantified total drops it
    assert after["moves"][0]["feedback"] == "dismissed"
    assert after["moves"][0]["saving_paise"] == 80_000

    # upsert: adopting flips the same row back and the saving counts again
    memory.record_feedback(session, ORG_A, memory.GST_LATEFEE, "adopted", now=NOW)
    assert memory.playbook_moves(session, ORG_A, facts)["quantified_saving_paise"] == 80_000
    assert len(session.scalars(select(PlaybookFeedback)).all()) == 1


def test_playbook_uses_the_statutory_engine_cap_not_a_naive_per_day(session):
    # 300 days × ₹50 = ₹15,000 naive; s.47 caps late fee at ₹10,000 (gst_calc._LATE_FEE_CAP).
    out = memory.playbook_moves(session, ORG_A, {"gstr3b_days_late": 300})
    assert out["quantified_saving_paise"] == 1_000_000


def test_feedback_is_sealed_and_unknown_playbook_is_refused(session):
    with pytest.raises(memory.UnknownPlaybook):
        memory.record_feedback(session, ORG_A, "NO-SUCH-PLAYBOOK", "dismissed", now=NOW)
    assert session.scalars(select(PlaybookFeedback)).all() == []

    memory.record_feedback(session, ORG_A, memory.GST_LATEFEE, "dismissed", now=NOW)
    chain = load_chain_for(session, ORG_A.org_id)
    assert [e.action for e in chain] == ["playbook.dismissed"]
    assert chain[0].query == memory.GST_LATEFEE
    assert verify_chain_for(session, ORG_A.org_id)
