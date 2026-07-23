"""P1-4 — investor-preview JSON: badged shape + the null-runway honesty contract.

What is pinned (not shape-checking):
  1. Every money figure carries a badge decided by ``badge_state`` — no KPI key is
     Mahsa-ported, so every state is EXACTLY ``honest_pending``; a ``verified`` here
     means someone hardcoded a badge instead of asking the coverage map (§0.4).
  2. The WS7-E2E fix survives the wrapper: the payload carries ``runway_months`` +
     ``accounts`` RAW and never the email template's pre-baked "∞" string, so the SPA
     can distinguish "empty ledger" from "genuinely not burning" instead of guessing.
  3. The wrapper is verbatim over ``investor_update``: period/cap-table/highlights
     match the generator's own output for the same session — no re-derivation.
  4. No send path exists on this surface — sending stays on the HTMX /investor page.

RBAC for the route is proven over real signed tokens by test_rbac_matrix.py (the
``POST /api/investor/preview`` row added there); this file is payload semantics only,
same split as test_api_statements.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.money import Paise
from app.core.principal import Principal
from app.core.rbac import Role
from app.core.strategy import investor_update
from app.db.models.treasury import BankAccount, BankTransaction
from app.web.api_investor import router

pytestmark = pytest.mark.integration


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    from app.db.session import get_session

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    return TestClient(app)


def _seed_treasury(session: Session) -> None:
    acct = BankAccount(
        bank_name="HDFC",
        account_number="1",
        ifsc="HDFC0000001",
        opening_balance=Paise.from_rupees(1200000),
        current_balance=Paise.from_rupees(1200000),
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id, txn_date="2026-05-15", debit=Paise.from_rupees(900000), credit=0
        )
    )
    session.add(
        BankTransaction(
            account_id=acct.id, txn_date="2026-05-16", debit=0, credit=Paise.from_rupees(300000)
        )
    )
    session.commit()


def test_preview_is_badged_and_matches_the_generator(session: Session) -> None:
    _seed_treasury(session)
    body = (
        _client(session)
        .post("/api/investor/preview", json={"highlights": ["Closed seed round", "  ", ""]})
        .json()
    )

    # verbatim over the generator — same session, same day, same composition
    upd = investor_update(session, datetime.now(UTC).date(), highlights=["Closed seed round"])
    assert body["period"] == upd["period"]
    assert body["cap_table"] == upd["cap_table"]
    # whitespace-only highlights are dropped, real ones pass through untouched
    assert body["highlights"] == ["Closed seed round"]

    figures = {f["key"]: f for f in body["figures"]}
    assert set(figures) == {"cash_paise", "net_burn_paise", "ar_paise"}
    for fig in figures.values():
        assert set(fig) == {"key", "label", "value", "raw", "state"}
        # §0.4: no KPI key is in Mahsa's ported coverage — nothing may claim ✓ here.
        assert fig["state"] == "honest_pending"
    assert figures["cash_paise"]["raw"] == upd["cash"]
    # money renders through the ONE canonical Indian-grouping renderer, server-side
    assert figures["cash_paise"]["value"] == Paise(upd["cash"]).format_inr()

    # the honest-runway facts arrive raw (accounts wired, really burning -> a real number)
    assert body["accounts"] == 1
    assert body["runway_months"] == 6.0
    # sending is a link-out, never wired here
    assert body["send_via"] == "/investor"


def test_empty_ledger_ships_raw_null_runway_never_infinity(session: Session) -> None:
    """The WS7-E2E fix, end to end: an empty ledger's null runway reaches the SPA as
    ``null`` + ``accounts: 0`` so the client renders the empty-ledger sentence — the
    pre-baked "∞" (a flattering lie for a new user) must never appear in this payload."""
    resp = _client(session).post("/api/investor/preview", json={})
    body = resp.json()
    assert body["runway_months"] is None
    assert body["accounts"] == 0
    assert "∞" not in resp.text
    # honest-empty is not ₹0-as-a-claim: raw zeros are the ledger's structural state and the
    # SPA's kpiValue/runwayText logic decides the sentence; the badge stays honest_pending.
    for fig in body["figures"]:
        assert fig["state"] == "honest_pending"


def test_preview_has_no_send_route(session: Session) -> None:
    """Do NOT wire sending (ticket): the only route this router exposes is the preview."""
    assert [(r.path, sorted(r.methods - {"HEAD"})) for r in router.routes] == [
        ("/api/investor/preview", ["POST"])
    ]
