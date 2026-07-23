"""SPEC-MEMCITE-1.0 MEM.P1-1 + MEM.P1-3 — nightly memory evolution and recall polish.

Pinned, mutation-proof:
  * evolve heals a drifted (unconsolidated) block via the SAME soft/temporal update the write
    path uses — archive + sealed ``memory.update``, attributed to ``system:evolve``;
  * evolve is idempotent: the second run changes nothing and seals nothing (double-run no-op);
  * the archive prune is bounded (KEEP_VERSIONS) and never touches the sealed audit chain;
  * the jobs loop runs evolve per org under the (org, job, period) ledger — a same-day re-run
    is a recorded skip, and ``all`` includes evolve (that is what makes it nightly);
  * recall query rewrite is expansion-only (alias + plural fold) and the recency post-filter
    ranks the most recent of the good matches first — both deterministic and LLM-free.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core import audit_store, memory
from app.core.audit_store import load_chain_for, verify_chain_for
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.memory import OrgMemory
from app.jobs import run_evolve, run_once

ORG_A = Principal(user_id="user-a", org_id="org-a", role=Role.OWNER, email="a@example.com")
NOW = "2026-07-23T20:00:00+00:00"


def _dirty_block(session: Session, org_id: str = "org-a") -> None:
    """Simulate drift past the write path (direct DB edit / import): duplicates the write
    path would have consolidated away."""
    session.add(
        OrgMemory(
            org_id=org_id,
            kind=memory.KIND_CFO,
            content="- Prefer old regime\n- prefer OLD regime\n- Quarterly reviews",
            updated_at=NOW,
            updated_by="import",
        )
    )
    session.flush()


# ---- evolve: heal + seal + idempotency ---------------------------------------------------


def test_evolve_reconsolidates_archives_and_seals_as_system(session: Session) -> None:
    _dirty_block(session)
    out = memory.evolve(session, "org-a", now=NOW)
    assert out == {"consolidated": True, "history_pruned": 0}

    row = session.scalars(select(OrgMemory)).one()
    assert row.content == "- Prefer old regime\n- Quarterly reviews"
    assert row.updated_by == memory.EVOLVE_USER

    # the prior (dirty) version was archived, linked to a REAL sealed memory.update event
    trail = memory.get_history(session, ORG_A)
    assert len(trail) == 1
    assert "prefer OLD regime" in trail[0]["content"]
    assert trail[0]["superseded_by"] == memory.EVOLVE_USER
    assert trail[0]["audit_seq"] is not None

    chain = load_chain_for(session, "org-a")
    assert [e.action for e in chain] == ["memory.update"]
    assert chain[0].user_id == memory.EVOLVE_USER
    assert verify_chain_for(session, "org-a")
    # hashes only in the sealed query — never memory content (write-path invariant holds here)
    assert "Prefer old regime" not in (chain[0].query or "")


def test_evolve_second_run_is_a_noop_nothing_sealed(session: Session) -> None:
    _dirty_block(session)
    memory.evolve(session, "org-a", now=NOW)
    again = memory.evolve(session, "org-a", now="2026-07-24T20:00:00+00:00")
    assert again == {"consolidated": False, "history_pruned": 0}
    assert len(load_chain_for(session, "org-a")) == 1  # no new seal
    assert len(memory.get_history(session, ORG_A)) == 1  # no new archive row


def test_evolve_on_empty_or_clean_org_is_a_noop(session: Session) -> None:
    assert memory.evolve(session, "org-a", now=NOW) == {
        "consolidated": False,
        "history_pruned": 0,
    }
    memory.set_cfo(session, ORG_A, "- already clean", now=NOW)
    assert memory.evolve(session, "org-a", now=NOW)["consolidated"] is False


def test_evolve_prunes_history_to_the_bounded_window_keeping_newest(session: Session) -> None:
    assert memory.KEEP_VERSIONS == 20  # the api-nest retention default, ported unchanged
    for i in range(6):
        memory.set_cfo(session, ORG_A, f"- version {i}", now=NOW)
    assert len(memory.get_history(session, ORG_A)) == 5

    out = memory.evolve(session, "org-a", now=NOW, keep_versions=2)
    assert out["history_pruned"] == 3
    kept = [h["content"] for h in memory.get_history(session, ORG_A)]
    assert kept == ["- version 4", "- version 3"]  # newest kept, oldest dropped
    # the prune bounds the ARCHIVE only — the sealed chain is untouched and still verifies
    assert len(load_chain_for(session, "org-a")) == 6
    assert verify_chain_for(session, "org-a")
    # already within the window -> a re-run prunes nothing (idempotent)
    assert memory.evolve(session, "org-a", now=NOW, keep_versions=2)["history_pruned"] == 0


# ---- jobs loop wiring (per-org, ledger-idempotent, part of `all`) ------------------------


def test_run_evolve_legacy_pass_walks_orgs_with_memory_rows(session: Session) -> None:
    _dirty_block(session, "org-a")
    _dirty_block(session, "org-b")
    out = run_evolve(session, None, now=NOW)
    assert out == {"job": "evolve", "memory_orgs": 2, "consolidated": 2, "history_pruned": 0}
    assert run_evolve(session, None, now=NOW)["consolidated"] == 0  # second pass: no-op


async def test_jobs_evolve_command_is_ledger_idempotent_per_period() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.db.models.shared import Org

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    s = factory()
    s.add(Org(id="org-a", name="org-a"))
    _dirty_block(s, "org-a")
    s.commit()
    s.close()

    now = datetime(2026, 7, 23, 20, 0, tzinfo=UTC)
    first = await run_once("evolve", settings=Settings(), now_utc=now, factory=factory)
    assert first["summary"] == {
        "command": "evolve",
        "period": "2026-07-23",
        "orgs": 1,
        "ok": 1,
        "failed": 0,
        "skipped": 0,
    }
    (res,) = first["results"]
    assert res["job"] == "evolve" and res["consolidated"] == 1

    second = await run_once("evolve", settings=Settings(), now_utc=now, factory=factory)
    assert second["summary"]["skipped"] == 1 and second["summary"]["ok"] == 0
    assert second["results"][0]["skipped"] == "already ran"

    s = factory()
    assert len(load_chain_for(s, "org-a")) == 1  # the whole day sealed exactly one event
    s.close()


# ---- MEM.P1-3: query rewrite + recency post-filter ---------------------------------------


def _seal_decision(session: Session, org: str, query: str, action: str, ts: str) -> str:
    entry = audit_store.append_for(
        session,
        org,
        {
            "timestamp": ts,
            "action": action,
            "domain": action.split(".")[0],
            "user_id": "founder",
            "query": query,
            "intent_global": None,
            "intent_domain": None,
            "validation_status": "green",
            "rules_version": "test",
        },
    )
    return entry.this_hash


def test_rewrite_alias_bridges_user_phrasing_to_domain_vocabulary(session: Session) -> None:
    h = _seal_decision(
        session, "org-a", "payroll run approved for june", "payroll.fold", "2026-07-01"
    )
    # "salary" appears NOWHERE in the sealed entry — only the alias reaches it
    recalled = memory.recall_decisions(session, ORG_A, "salary decision?")
    assert [r["audit_hash"] for r in recalled] == [h]


def test_rewrite_normalises_gstr3b_and_folds_plurals(session: Session) -> None:
    h = _seal_decision(session, "org-a", "gstr-3b filing decision", "gst.fold", "2026-07-01")
    assert [r["audit_hash"] for r in memory.recall_decisions(session, ORG_A, "gstr3b?")] == [h]
    # plural query token, singular entry token
    assert [r["audit_hash"] for r in memory.recall_decisions(session, ORG_A, "filings gst")] == [h]


def test_rewrite_is_expansion_only_never_redirects(session: Session) -> None:
    # An entry matching the LITERAL token still matches after rewrite (nothing dropped).
    h = _seal_decision(
        session, "org-a", "vendor onboarding decision", "payables.fold", "2026-07-01"
    )
    assert [r["audit_hash"] for r in memory.recall_decisions(session, ORG_A, "vendor?")] == [h]


def test_recency_post_filter_ranks_recent_decisions_first(session: Session) -> None:
    """The MEM.P1-3 Verify line: an OLD entry with the higher lexical score no longer buries
    a recent decision that also matches."""
    old = _seal_decision(
        session, "org-a", "gstr-3b filing decision recorded", "gst.fold", "2026-01-05"
    )
    recent = _seal_decision(session, "org-a", "gstr-3b noted", "gst.fold", "2026-07-20")
    # old scores higher lexically (filing+decision+gstr-3b) than recent (gstr-3b only)…
    recalled = memory.recall_decisions(session, ORG_A, "gstr-3b filing decision?")
    assert [r["audit_hash"] for r in recalled] == [recent, old]  # …but recent ranks first


def test_recall_polish_is_deterministic(session: Session) -> None:
    for i in range(5):
        _seal_decision(session, "org-a", f"gst filing note {i}", "gst.fold", f"2026-07-{10 + i}")
    a = memory.recall_decisions(session, ORG_A, "gst filings?")
    b = memory.recall_decisions(session, ORG_A, "gst filings?")
    assert a == b and len(a) == 3  # byte-identical, still bounded by limit
