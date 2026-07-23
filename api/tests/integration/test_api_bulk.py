"""WS7.5 — POST /api/inbox/bulk against the REAL app and the REAL Mahsa binary.

The four contract properties, each pinned by a test that fails if the property breaks:
  (a) ``confirm`` omitted/false is a pure dry-run — the audit chain does not grow;
  (b) an id that is not actionable is reported as *skipped with a reason*, never silently dropped;
  (c) an unknown action is rejected (400) before anything is fetched or written;
  (d) Mahsa unreachable => nothing is mutated, and the response says so.

Plus (e): confirm=true really does seal decisions — without it, (a) and (d) would pass vacuously
against an endpoint that never commits at all.
"""

import os

import pytest

# Must be set before importing app.main (module instantiates the app at import time).
os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.audit_store import load_chain  # noqa: E402
from app.core.betterauth import TOKEN_COOKIE, get_principal  # noqa: E402
from app.core.mahsa_client import MahsaClient  # noqa: E402
from app.core.money import Paise  # noqa: E402
from app.core.principal import Principal  # noqa: E402
from app.core.rbac import Role  # noqa: E402
from app.db.models.treasury import BankAccount, BankTransaction  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_mahsa  # noqa: E402
from app.main import app  # noqa: E402
from app.web.api_bulk import router as bulk_router  # noqa: E402

pytestmark = pytest.mark.integration

# The orchestrator wires this router in app/main.py; until it does, mount it here so these tests
# exercise the real app. Idempotent, so it stays correct once main.py includes it for real.
if not any(getattr(r, "path", None) == "/api/inbox/bulk" for r in app.routes):
    app.include_router(bulk_router)

TREASURY_ID = "approval:treasury"


def _login(client: TestClient, env) -> None:
    # P2-6: the password login is deleted — the middleware wants a real Better Auth JWT, here
    # carried the HTMX way in the `maisha_jwt` cookie (signed by the fixture's live JWKS).
    client.cookies.set(TOKEN_COOKIE, env.token)


def _seed_distressed_treasury(session) -> None:
    """₹3,00,000 cash against ₹9,00,000 burned -> ~1 month runway -> Mahsa returns a RED verdict
    with requires_approval, which is what puts a real, selectable item in the inbox."""
    acct = BankAccount(
        bank_name="HDFC",
        account_number="1",
        ifsc="HDFC0000001",
        current_balance=Paise.from_rupees(300000),
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id, txn_date="2026-05-10", debit=Paise.from_rupees(900000), credit=0
        )
    )
    session.commit()


@pytest.fixture
def live(session, mahsa_server, betterauth_owner_env):
    """The app wired to a real Mahsa and an isolated seeded DB."""
    _seed_distressed_treasury(session)
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_server)
    app.dependency_overrides[get_session] = lambda: session
    # WS5.1: /api/inbox/bulk is capability-gated (read to preview, approve_payment to commit).
    # The legacy shared-password cookie carries NO role, so it can no longer answer for this
    # route. This file tests bulk semantics, not RBAC — override the auth seam with an Owner and
    # leave the matrix to tests/integration/test_rbac_matrix.py.
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    client = TestClient(app)
    _login(client, betterauth_owner_env)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def mahsa_down(session, betterauth_owner_env):
    """Same app and DB, but the ambient Mahsa URL is a dead port (see tests/conftest.py)."""
    _seed_distressed_treasury(session)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    client = TestClient(app)
    _login(client, betterauth_owner_env)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_live_inbox_has_the_seeded_approval(live):
    """Guard for the tests below: they are only meaningful if a real eligible item exists."""
    body = live.get("/api/inbox").json()
    assert body["mahsa_up"] is True
    assert TREASURY_ID in [i["id"] for i in body["items"]]


# ── (a) dry-run mutates nothing ───────────────────────────────────────────────
def test_dry_run_previews_and_mutates_nothing(live, session):
    before = len(load_chain(session))

    resp = live.post("/api/inbox/bulk", json={"action": "approve", "ids": [TREASURY_ID]})
    assert resp.status_code == 200
    body = resp.json()

    assert body["mahsa_up"] is True
    assert body["committed"] is False
    assert body["committed_count"] == 0
    assert [r["id"] for r in body["rows"]] == [TREASURY_ID]
    assert body["rows"][0]["will"]  # states exactly what would change

    # Nothing was written: the hash-chained audit log did not grow, and the item is still pending.
    assert len(load_chain(session)) == before
    assert TREASURY_ID in [i["id"] for i in live.get("/api/inbox").json()["items"]]


def test_dry_run_never_invents_a_rupee_total(live):
    """The seeded treasury approval has no quantified ₹ at stake. The total must come back null
    ("not yet known"), never a confident ₹0 (contract §2.2)."""
    body = live.post("/api/inbox/bulk", json={"action": "approve", "ids": [TREASURY_ID]}).json()
    assert body["rows"][0]["impact_paise"] is None
    assert body["total_impact_paise"] is None, "unknown impact must not render as 0"
    assert body["unquantified_rows"] == 1


# ── (b) ineligible ids are reported, not dropped ──────────────────────────────
def test_ineligible_id_is_reported_skipped_with_a_reason(live):
    bogus = "approval:no-such-domain"
    body = live.post(
        "/api/inbox/bulk", json={"action": "approve", "ids": [TREASURY_ID, bogus]}
    ).json()

    accounted = {r["id"] for r in body["rows"]} | {s["id"] for s in body["skipped"]}
    assert accounted == {TREASURY_ID, bogus}, "every submitted id must be accounted for"

    skipped = {s["id"]: s for s in body["skipped"]}
    assert bogus in skipped, "an unactionable id must be reported skipped, not silently dropped"
    assert skipped[bogus]["reason"].strip(), "a skipped row must say WHY it was skipped"
    assert "unknown" in skipped[bogus]["reason"].lower()
    # It is skipped, not quietly folded into the eligible set.
    assert bogus not in [r["id"] for r in body["rows"]]


# ── (c) unknown action rejected ───────────────────────────────────────────────
def test_unknown_action_is_rejected(live):
    resp = live.post("/api/inbox/bulk", json={"action": "delete-everything", "ids": [TREASURY_ID]})
    assert resp.status_code == 400
    assert "delete-everything" in resp.json()["detail"]


def test_unknown_action_rejected_before_any_write(live, session):
    before = len(load_chain(session))
    resp = live.post(
        "/api/inbox/bulk",
        json={"action": "approve-all-silently", "ids": [TREASURY_ID], "confirm": True},
    )
    assert resp.status_code == 400
    assert len(load_chain(session)) == before


# ── (d) Mahsa down commits nothing ────────────────────────────────────────────
def test_mahsa_down_commits_nothing_and_says_so(mahsa_down, session):
    before = len(load_chain(session))

    resp = mahsa_down.post(
        "/api/inbox/bulk", json={"action": "approve", "ids": [TREASURY_ID], "confirm": True}
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["mahsa_up"] is False  # stated, never absorbed into a thinner response
    assert body["committed"] is False
    assert body["committed_count"] == 0
    assert body["rows"] == []
    assert "nothing was changed" in body["note"].lower()
    assert body["total_impact_paise"] is None  # no invented ₹ while the gatekeeper is offline

    assert len(load_chain(session)) == before, "a confirm with Mahsa down must write nothing"


# ── (e) confirm=true actually commits (keeps the tests above non-vacuous) ─────
def test_confirm_seals_decisions_to_the_audit_chain(live, session):
    before = len(load_chain(session))

    body = live.post(
        "/api/inbox/bulk", json={"action": "approve", "ids": [TREASURY_ID], "confirm": True}
    ).json()

    assert body["committed"] is True
    assert body["committed_count"] == 1
    assert len(load_chain(session)) == before + 1  # exactly one decision sealed

    # The approval is resolved, so it drops out of the pending inbox.
    assert TREASURY_ID not in [i["id"] for i in live.get("/api/inbox").json()["items"]]


# ── (f) fix:bulk-rows — decisions carry row identity end-to-end ───────────────
def test_two_rows_one_domain_seal_two_distinguishable_decisions(live, session, monkeypatch):
    """Two previewed rows in ONE domain must seal two decisions that name their rows — never
    two byte-identical domain-level entries. Mutation check: if row identity is dropped from
    the confirm loop, the two audit queries collapse into identical strings and the per-row
    ``item_id`` asserts fail."""
    from sqlalchemy import select

    from app.db.models.shared import Decision
    from app.web import api_bulk
    from app.web.exceptions import InboxItem

    def _two_rows_one_domain(approvals, blocked):
        return [
            InboxItem(
                id=rid,
                queue="awaiting_approval",
                what=f"{rid} needs sign-off",
                when=None,
                impact_paise=None,
                impact_label="Sign-off pending (₹ not quantified)",
                action_label="Review & approve",
                domain="treasury",
                selectable=True,
            )
            for rid in ("approval:treasury", "approval:treasury:sweep")
        ]

    monkeypatch.setattr(api_bulk, "build_items", _two_rows_one_domain)
    before = len(load_chain(session))

    body = live.post(
        "/api/inbox/bulk",
        json={
            "action": "approve",
            "ids": ["approval:treasury", "approval:treasury:sweep"],
            "confirm": True,
        },
    ).json()

    assert body["committed"] is True
    assert body["committed_count"] == 2  # rows actually decided, not domains touched

    chain = load_chain(session)
    assert len(chain) == before + 2
    q1, q2 = chain[-2].query, chain[-1].query
    assert q1 != q2, "two rows in one domain must be distinguishable in the audit log"
    assert "[row approval:treasury]" in (q1 or "")
    assert "[row approval:treasury:sweep]" in (q2 or "")

    decided = [r.item_id for r in session.scalars(select(Decision)).all()]
    assert decided == ["approval:treasury", "approval:treasury:sweep"]


def test_confirm_rejects_ids_outside_the_preview(live, session):
    """Confirm processes exactly the previewed ids: a stray id is rejected with a reason and
    never decided — no audit entry, no Decision row names it."""
    from sqlalchemy import select

    from app.db.models.shared import Decision

    stray = "approval:no-such-domain"
    before = len(load_chain(session))

    body = live.post(
        "/api/inbox/bulk",
        json={"action": "approve", "ids": [TREASURY_ID, stray], "confirm": True},
    ).json()

    assert body["committed_count"] == 1  # only the previewed row was decided
    assert [r["id"] for r in body["rows"]] == [TREASURY_ID]
    skipped = {s["id"]: s for s in body["skipped"]}
    assert stray in skipped and skipped[stray]["reason"].strip()

    chain = load_chain(session)
    assert len(chain) == before + 1
    assert "[row approval:treasury]" in (chain[-1].query or "")
    assert all(stray not in (e.query or "") for e in chain), "stray id must never be decided"
    assert [r.item_id for r in session.scalars(select(Decision)).all()] == [TREASURY_ID]
