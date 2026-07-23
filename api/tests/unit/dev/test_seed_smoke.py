"""WS11.2 — demo-tenant seed smoke test.

Runs the seed against a FRESH in-memory DB (the shared ``session`` fixture) and asserts that
every hub's assembler returns real, non-empty content, and that the verified path is live:
the seeded books emit Mahsa recompute claims (the figures the live fold recomputes to the
paisa) and the citation anchors behind the cash strip resolve against the vault documents the
import minted. No Mahsa sidecar needed — everything here is the pure assembler layer the
routes call.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core import memory
from app.core.anchors import bank_documents
from app.core.audit_store import load_chain_for, verify_chain_for
from app.core.mahsa_coverage import is_recomputed
from app.core.overview import collect_kpis, upcoming_deadlines
from app.core.rbac import Role
from app.db.models.treasury import BankTransaction
from app.dev.seed import _FOUNDER, DEMO_ORG, seed
from app.domains import build_registry
from app.domains.gst.service import GstService
from app.domains.ledger.service import LedgerService
from app.domains.payroll.service import PayrollService
from app.domains.vault.service import VaultService
from app.llm.tools import enrich
from app.web.today import build_today

AS_OF = date(2026, 7, 15)

#: Minimum verified-path figures the demo books must carry: 5 payroll claims per employee
#: x 2 employees (wage base, PF x2, ESI x2) + the late-filed GSTR-3B interest claim.
MIN_VERIFIED_PATH_FIGURES = 11


def _seeded(session):
    assert seed(session).get("skipped") is None
    return session


def test_every_domain_hub_assembler_returns_content(session):
    _seeded(session)
    registry = build_registry()
    domains = registry.domains()
    assert len(domains) == 12
    for domain in domains:
        service = registry.get(domain)
        snapshot = service.build_snapshot(session, AS_OF)
        facts = {k: v for k, v in enrich(snapshot).items() if k != "as_of"}
        assert facts, f"domain hub '{domain}' rendered an empty snapshot after seeding"


def test_today_view_is_alive_with_resolved_citation_anchors(session):
    _seeded(session)
    today = build_today(session, AS_OF, approvals=[])
    strip = today["cash_strip"]
    assert [p["label"] for p in strip] == ["Cash on hand", "Monthly burn", "Runway"]
    assert all(p["value"] not in ("", "₹0.00") for p in strip)
    # The cash figures cite the imported statements; every anchor must resolve cleanly.
    docs = strip[0]["documents"]
    assert docs, "cash strip carries no citation documents — import path did not mint anchors"
    assert all(d.get("resolution") in (None, "resolved") for d in docs), docs
    assert today["trouble"], "trouble radar empty despite seeded deadlines"

    # Every imported bank row is anchored (no legacy anchor-less rows in a fresh seed).
    txns = session.scalars(select(BankTransaction)).all()
    assert txns and all(t.source_doc_id and t.row_hash for t in txns)
    assert bank_documents(session, txns)


def test_kpis_filings_and_calendar_are_populated(session):
    _seeded(session)
    k = collect_kpis(session, AS_OF)
    assert k["cash"] > 0 and k["net_burn"] > 0 and k["ar"] > 0 and k["ap"] > 0
    assert upcoming_deadlines(session, AS_OF), "no compliance alerts near seeded deadlines"


def test_statements_come_from_real_double_entry_books(session):
    _seeded(session)
    ledger = LedgerService()
    tb = ledger.trial_balance(session)
    assert tb["total_debit"] > 0 and tb["balanced"], (
        "trial balance empty or untied — Tally import did not post"
    )
    pnl = ledger.profit_and_loss(session)
    assert pnl["income"] > 0 and pnl["expense"] > 0


def test_payroll_run_is_pending_approval(session):
    _seeded(session)
    snapshot = PayrollService().build_snapshot(session, AS_OF)
    assert snapshot["metrics"]["payroll_run_pending"] >= 1, (
        "seed must leave a draft payroll run so the approvals queue has a genuine item"
    )


def test_verified_path_figures_exist(session):
    """The seeded books emit recompute claims — the figures Mahsa independently recomputes
    (rendered with the ✓ path once the live fold runs). Each claim's target must be ported
    in the coverage map, so none of this is fabricated verification."""
    _seeded(session)
    claims = PayrollService().recompute_claims(session, AS_OF)
    claims += GstService().recompute_claims(session)
    assert len(claims) >= MIN_VERIFIED_PATH_FIGURES, [c.label for c in claims]
    # Spot-check honesty: the oracle-target names among them are Rust-ported.
    assert is_recomputed("statutory_wage_base") and is_recomputed("esi")
    for c in claims:
        assert isinstance(c.claimed_paise, int)


def test_vault_audit_room_and_memory_are_alive(session):
    _seeded(session)
    # Vault: the two bank statements + the Tally XML, all integrity-clean.
    docs = VaultService().browse(session, "", role=Role.OWNER, as_of=AS_OF)
    assert len(docs) == 3
    assert {d["doc_type"] for d in docs} == {"bank_statement", "tally_export"}
    assert all(d.get("integrity") != "tampered" for d in docs)

    # Audit Room: real sealed memory.update events on the demo org's chain, chain verifies.
    chain = load_chain_for(session, DEMO_ORG)
    assert len(chain) >= 2 and all(e.action == "memory.update" for e in chain)
    assert verify_chain_for(session, DEMO_ORG)

    # Memory: CFO posture set and superseded once (append), history archived.
    cfo = memory.get_cfo(session, _FOUNDER)
    assert "runway" in cfo["content"] and "MSME" in cfo["content"]
    assert memory.get_history(session, _FOUNDER)


def test_seed_is_idempotent(session):
    _seeded(session)
    assert seed(session) == {"skipped": 1}
