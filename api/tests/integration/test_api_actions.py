"""P0-2 — the generic action preview/commit machinery (INVARIANT 9: no silent mutation).

What is actually pinned here (each names the mutation it kills):
  1. A preview writes NOTHING — asserted by row-count on the action's own table for all five
     registry actions. Kills: dropping the ``db.rollback()`` dry-run gate in ``action_preview``.
  2. A commit without a preview token — or with values edited after the preview — is a 409 and
     writes nothing. Kills: dropping the ``hmac.compare_digest`` gate in ``action_commit``.
  3. Preview → commit with the echoed token creates exactly one row and returns badged
     after-figures whose states come from ``badge_state`` (never a fabricated "verified" for a
     non-coverage fact). Kills: hardcoding ``state`` in the response.
  4. Capability negatives PER ACTION: a read-only role (CA) can preview every action and can
     commit none. Kills: dropping ``require(Capability.WRITE)`` from the commit route.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.equity import Shareholder
from app.db.models.expense import ExpenseClaim
from app.db.models.ledger import ChartOfAccounts
from app.db.models.shared import ComplianceCalendar
from app.db.models.vault import Document
from app.db.session import get_session
from app.web.api_actions import router

pytestmark = pytest.mark.integration

# (domain, key) -> (the table the action writes, a valid form payload)
CASES = {
    ("ledger", "create-account"): (
        ChartOfAccounts,
        {"code": "1000", "name": "Cash", "account_type": "asset"},
    ),
    ("compliance", "add-deadline"): (
        ComplianceCalendar,
        {
            "domain": "gst",
            "form_name": "GSTR-3B (Jun)",
            "due_date": "2026-08-20",
            "filing_period": "2026-06",
        },
    ),
    ("equity", "add-shareholder"): (
        Shareholder,
        {"name": "Founder", "category": "founder", "shares_held": "700000"},
    ),
    ("expense", "submit-claim"): (
        ExpenseClaim,
        {
            "claim_date": "2026-07-01",
            "expense_date": "2026-06-28",
            "category": "travel",
            "amount": "5000.50",
        },
    ),
    ("vault", "ingest"): (
        Document,
        {
            "file_name": "contract.pdf",
            "content": "master services agreement",
            "upload_date": "2026-07-01",
        },
    ),
}


def _client(session: Session, role: Role = Role.OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    # Payload-semantics tests use the blessed get_principal override (same pattern as
    # test_api_domains.py); the full route x role matrix over real signed tokens lives in
    # test_rbac_matrix.py, which also covers these two routes via API_ROUTE_GATES.
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    return TestClient(app, raise_server_exceptions=True)


def _count(session: Session, table) -> int:
    return session.scalar(select(func.count()).select_from(table)) or 0


def test_preview_mutates_nothing_for_every_action(session):
    """Kills: removing the unconditional rollback after the dry-run handler call."""
    client = _client(session)
    for (domain, key), (table, values) in CASES.items():
        before = _count(session, table)
        body = client.post(f"/api/domains/{domain}/actions/{key}/preview", json={"values": values})
        assert body.status_code == 200, body.text
        data = body.json()
        assert data["committed"] is False
        assert data["will_create"]  # the handler's own message — real validation ran
        assert data["preview_token"]
        # normalized echo covers every submitted field
        for k, v in values.items():
            assert data["normalized"][k] == v
        assert _count(session, table) == before, f"{domain}/{key} preview mutated the DB"


def test_commit_without_preview_token_is_rejected_and_writes_nothing(session):
    """Kills: dropping the hmac.compare_digest gate (commit-without-preview)."""
    client = _client(session)
    for (domain, key), (table, values) in CASES.items():
        before = _count(session, table)
        for token in ("", "deadbeef" * 8):
            body = client.post(
                f"/api/domains/{domain}/actions/{key}/commit",
                json={"values": values, "preview_token": token},
            )
            assert body.status_code == 409, f"{domain}/{key}: {body.text}"
            assert "Nothing was changed" in body.json()["detail"]
        assert _count(session, table) == before


def test_commit_with_tampered_values_is_rejected(session):
    """The token binds the EXACT normalized values: edit-after-preview must re-preview."""
    client = _client(session)
    values = CASES[("ledger", "create-account")][1]
    token = client.post(
        "/api/domains/ledger/actions/create-account/preview", json={"values": values}
    ).json()["preview_token"]
    tampered = {**values, "name": "Slush fund"}
    body = client.post(
        "/api/domains/ledger/actions/create-account/commit",
        json={"values": tampered, "preview_token": token},
    )
    assert body.status_code == 409
    assert _count(session, ChartOfAccounts) == 0


def test_preview_then_commit_creates_with_badged_after_figures(session):
    client = _client(session)
    for (domain, key), (table, values) in CASES.items():
        before = _count(session, table)
        preview = client.post(
            f"/api/domains/{domain}/actions/{key}/preview", json={"values": values}
        ).json()
        body = client.post(
            f"/api/domains/{domain}/actions/{key}/commit",
            json={"values": values, "preview_token": preview["preview_token"]},
        )
        assert body.status_code == 200, body.text
        data = body.json()
        assert data["committed"] is True
        assert data["created"]
        assert _count(session, table) == before + 1, f"{domain}/{key} commit wrote nothing"
        # after-figures come from the SAME §0.4 badge machinery as GET /domains/{d}: every
        # state is a known badge value, and unknown facts fall to honest_pending, never ✓.
        assert data["after_figures"], f"{domain}/{key}: no after-figures returned"
        assert all(f["state"] in ("verified", "honest_pending") for f in data["after_figures"])


def test_money_field_previews_exact_paise_and_is_never_hardcoded_verified(session):
    """The expense amount echo: rupees in, exact paise figure out — badged ◐ because an input
    echo is not a Mahsa coverage target (unknown falls to unverified, §0.4)."""
    client = _client(session)
    values = CASES[("expense", "submit-claim")][1]
    figures = client.post(
        "/api/domains/expense/actions/submit-claim/preview", json={"values": values}
    ).json()["figures"]
    paise = {f["key"]: f for f in figures}["expense_amount_paise"]
    assert paise["raw"] == 500050  # ₹5000.50 exactly, half-up, no float drift
    assert paise["state"] == "honest_pending"


def test_expense_preview_surfaces_the_policy_limit_warning(session):
    """P1-8: the ActionDrawer's preview panel renders `will_create` verbatim — so the existing
    per-category policy check (``expense_calc.check_policy``, already enforced by EXPENSE-001 on
    the snapshot) must show up as text IN THE PREVIEW, not just silently on the committed row."""
    client = _client(session)
    over_limit = client.post(
        "/api/domains/expense/actions/submit-claim/preview",
        json={
            "values": {
                "claim_date": "2026-07-01",
                "expense_date": "2026-06-28",
                "category": "meals",
                "amount": "3000",  # DEFAULT_POLICY["meals"] == 2000 -> ₹1,000 over
            }
        },
    ).json()
    assert "WARNING" in over_limit["will_create"]
    assert "policy limit" in over_limit["will_create"]
    assert "₹1,000" in over_limit["will_create"]  # the exact excess, not just a flag

    within_limit = client.post(
        "/api/domains/expense/actions/submit-claim/preview",
        json={
            "values": {
                "claim_date": "2026-07-01",
                "expense_date": "2026-06-28",
                "category": "meals",
                "amount": "1500",
            }
        },
    ).json()
    assert "WARNING" not in within_limit["will_create"]


def test_validation_errors_are_named_and_mutate_nothing(session):
    client = _client(session)
    # missing required field
    body = client.post(
        "/api/domains/ledger/actions/create-account/preview",
        json={"values": {"code": "1000", "name": "Cash"}},
    )
    assert body.status_code == 422
    assert any(e["field"] == "account_type" for e in body.json()["detail"]["errors"])
    # select outside the declared options
    body = client.post(
        "/api/domains/ledger/actions/create-account/preview",
        json={"values": {"code": "1000", "name": "Cash", "account_type": "slush"}},
    )
    assert body.status_code == 422
    assert _count(session, ChartOfAccounts) == 0


def test_unknown_action_is_a_real_404(session):
    client = _client(session)
    assert (
        client.post("/api/domains/gst/actions/no-such/preview", json={"values": {}}).status_code
        == 404
    )


def test_read_only_role_can_preview_every_action_but_commit_none(session):
    """Capability negatives per action (CA holds read, not write). Kills: dropping
    require(Capability.WRITE) from the commit route."""
    client = _client(session, role=Role.CA)
    for (domain, key), (table, values) in CASES.items():
        preview = client.post(
            f"/api/domains/{domain}/actions/{key}/preview", json={"values": values}
        )
        assert preview.status_code == 200, f"{domain}/{key}: CA must be able to size up a write"
        body = client.post(
            f"/api/domains/{domain}/actions/{key}/commit",
            json={"values": values, "preview_token": preview.json()["preview_token"]},
        )
        assert body.status_code == 403, f"{domain}/{key}: {body.text}"
        assert body.json()["detail"] == "missing capability: write"
        assert _count(session, table) == 0
