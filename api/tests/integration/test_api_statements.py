"""P1-5 — statements JSON: badged payload shape + a broken book stays broken in the payload.

What is pinned (not shape-checking):
  1. Every money figure carries a badge decided by ``badge_state`` — and since no ledger
     statement key is Mahsa-ported, every state is EXACTLY ``honest_pending``. A ``verified``
     here means someone hardcoded a badge instead of asking the coverage map (§0.4).
  2. An unbalanced book SURVIVES to the payload: ``balanced: false`` and the exact paise
     diff — the assembler never "corrects" or hides an imbalance (WS7 contract: a broken
     book must look broken).
  3. The GL drilldown returns the running balance to the paisa, and an unknown account is
     a real 404, not an empty statement.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.money import Paise
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.ledger import JournalEntry, JournalLine
from app.db.session import get_session
from app.domains.ledger.service import LedgerService
from app.web.api_statements import router

pytestmark = pytest.mark.integration


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    # Payload semantics only — the RBAC matrix proves the gates over real signed tokens
    # in test_rbac_matrix.py (same pattern as test_api_domains.py).
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    return TestClient(app)


def _books(session: Session) -> dict[str, int]:
    svc = LedgerService()
    ids = {
        "cash": svc.create_account(session, code="1000", name="Cash", account_type="asset"),
        "capital": svc.create_account(session, code="3000", name="Capital", account_type="equity"),
        "sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
    }
    svc.post_journal_entry(
        session,
        entry_date="2026-04-01",
        description="seed capital",
        lines=[
            {"account_id": ids["cash"], "debit": Paise.from_rupees(500000), "credit": 0},
            {"account_id": ids["capital"], "debit": 0, "credit": Paise.from_rupees(500000)},
        ],
    )
    svc.post_journal_entry(
        session,
        entry_date="2026-04-02",
        description="cash sale",
        lines=[
            {"account_id": ids["cash"], "debit": Paise.from_rupees(100000), "credit": 0},
            {"account_id": ids["sales"], "debit": 0, "credit": Paise.from_rupees(100000)},
        ],
    )
    session.commit()
    return ids


def test_statements_payload_is_badged_and_exact(session: Session) -> None:
    _books(session)
    body = _client(session).get("/api/statements").json()

    tb = body["trial_balance"]
    assert tb["balanced"] is True
    all_figures = tb["figures"] + body["pnl"]["figures"] + body["balance_sheet"]["figures"]
    assert len(all_figures) == 10
    for fig in all_figures:
        assert set(fig) == {"key", "label", "value", "raw", "state"}
        # §0.4: no ledger key is in Mahsa's ported coverage — nothing may claim ✓ here.
        assert fig["state"] == "honest_pending"

    by_key = {f["key"]: f for f in all_figures}
    assert by_key["total_debit_paise"]["raw"] == Paise.from_rupees(600000)
    assert by_key["total_credit_paise"]["raw"] == Paise.from_rupees(600000)
    assert by_key["trial_balance_diff_paise"]["raw"] == 0
    assert by_key["net_profit_paise"]["raw"] == Paise.from_rupees(100000)
    assert by_key["assets_paise"]["raw"] == Paise.from_rupees(600000)
    # money renders through the ONE canonical Indian-grouping renderer, server-side
    assert by_key["total_debit_paise"]["value"] == Paise.from_rupees(600000).format_inr()
    assert body["balance_sheet"]["balanced"] is True
    # the GL picker gets the real chart of accounts, code-ordered
    assert [a["code"] for a in body["accounts"]] == ["1000", "3000", "4000"]


def test_imbalance_flag_survives_to_payload(session: Session) -> None:
    ids = _books(session)
    # A genuinely broken book: a lone debit with no balancing credit, written straight to the
    # table the way a bug or a half-applied migration would — post_journal_entry refuses it.
    entry = JournalEntry(
        entry_date="2026-04-03",
        description="broken",
        source="manual",
        total_debit=12345,
        total_credit=0,
    )
    session.add(entry)
    session.flush()
    session.add(
        JournalLine(journal_entry_id=entry.id, account_id=ids["cash"], debit=12345, credit=0)
    )
    session.commit()

    body = _client(session).get("/api/statements").json()
    tb = body["trial_balance"]
    assert tb["balanced"] is False
    diff = {f["key"]: f for f in tb["figures"]}["trial_balance_diff_paise"]
    assert diff["raw"] == 12345  # the exact paise imbalance, not a rounded/hidden one
    assert diff["state"] == "honest_pending"
    # the extra debit landed on an asset account, so the accounting equation fails too
    assert body["balance_sheet"]["balanced"] is False


def test_general_ledger_drilldown_and_unknown_account_404(session: Session) -> None:
    ids = _books(session)
    client = _client(session)

    gl = client.get(f"/api/statements/gl/{ids['cash']}").json()
    assert gl["code"] == "1000"
    assert [ln["balance"] for ln in gl["lines"]] == [
        Paise.from_rupees(500000),
        Paise.from_rupees(600000),
    ]
    assert gl["closing"]["raw"] == Paise.from_rupees(600000)
    assert gl["closing"]["state"] == "honest_pending"
    assert gl["opening"]["raw"] == 0
    assert gl["state"] == "honest_pending"

    assert client.get("/api/statements/gl/999999").status_code == 404
