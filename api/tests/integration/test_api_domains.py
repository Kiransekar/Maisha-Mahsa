"""WS7.4 — the domains/audit JSON API against the REAL Mahsa binary.

What is actually pinned here (not shape-checking):
  1. No figure's badge state is ever a hardcoded "verified" — it comes from
     ``app.core.mahsa_coverage.badge_state`` only, so an ordinary snapshot fact (not a Mahsa
     coverage target) is honestly reported ``honest_pending``.
  2. Mahsa unreachable is STATED (``mahsa_up: false``) rather than silently absorbed — domain
     health is null, never a fabricated score.
  3. Unknown domain is a real 404, not a silent empty page.
  4. The Audit Room reports chain verification TRUTHFULLY, including a tampered chain.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.audit_store import append
from app.core.betterauth import get_principal
from app.core.mahsa_client import MahsaClient
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.shared import AuditLog
from app.db.session import get_session
from app.deps import get_mahsa
from app.web.api_domains import router

pytestmark = pytest.mark.integration


def _client(session: Session, mahsa_url: str) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_url)
    # WS5.1: these routes are capability-gated. This file tests the payload semantics, not
    # RBAC — override the one auth seam with an Owner (same pattern as test_api_bulk.py);
    # the matrix itself is proven over real signed tokens in test_rbac_matrix.py.
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    return TestClient(app)


def test_domains_list_has_live_health_and_honest_badges(session, mahsa_server):
    client = _client(session, mahsa_server)

    body = client.get("/api/domains").json()
    assert body["mahsa_up"] is True
    assert body["mahsa_down_message"] is None
    keys = {d["key"] for d in body["domains"]}
    assert keys == {
        "treasury", "revenue", "payables", "payroll", "gst", "tax",
        "ledger", "forecast", "equity", "compliance", "expense", "vault",
    }
    for d in body["domains"]:
        assert d["status"] in ("green", "yellow", "red")
        assert d["score"] is not None  # real Mahsa recompute, not a fabricated stub
        assert d["coverage"]["verified"] <= d["coverage"]["total"]
    assert "kpis" in body and "cash_fmt" in body["kpis"]
    assert isinstance(body["deadlines"], list)


def test_domains_list_states_mahsa_down_never_fabricates(session):
    client = _client(session, "http://127.0.0.1:9")  # nothing listening

    body = client.get("/api/domains").json()
    assert body["mahsa_up"] is False
    assert "unreachable" in body["mahsa_down_message"]
    for d in body["domains"]:
        assert d["score"] is None
        assert d["status"] is None
    # KPIs are direct DB reads and still render (they don't need Mahsa).
    assert "kpis" in body


def test_unknown_domain_is_404(session, mahsa_server):
    client = _client(session, mahsa_server)
    resp = client.get("/api/domains/not-a-real-domain")
    assert resp.status_code == 404


def test_domain_detail_never_hardcodes_verified(session, mahsa_server):
    client = _client(session, mahsa_server)

    body = client.get("/api/domains/ledger").json()
    assert body["domain"] == "ledger"
    assert body["mahsa_up"] is True
    assert body["figures"], "ledger should expose at least one snapshot figure"
    for f in body["figures"]:
        assert f["state"] in ("verified", "honest_pending")
    # A plain snapshot fact key (not a real coverage target) is never fabricated verified.
    assert any(f["state"] == "honest_pending" for f in body["figures"])
    # Ledger's action registry (app/web/actions.py) is surfaced, not re-derived here.
    assert any(a["key"] == "create-account" for a in body["actions"])
    assert all(e.get("domain") == "ledger" for e in body["deadlines"])


def test_audit_room_reports_a_tampered_chain_truthfully(session, mahsa_server):
    client = _client(session, mahsa_server)

    for i in range(3):
        append(
            session,
            {
                "timestamp": f"2026-07-2{i}T00:00:00Z",
                "action": "test.entry",
                "domain": "ledger",
                "user_id": "tester",
                "query": None,
                "intent_global": None,
                "intent_domain": None,
                "validation_status": "green",
                "rules_version": "v1",
            },
        )
    session.commit()

    body = client.get("/api/audit").json()
    assert body["chain_intact"] is True
    assert body["total"] == 3
    # Newest first.
    assert [e["timestamp"] for e in body["entries"]] == [
        "2026-07-22T00:00:00Z", "2026-07-21T00:00:00Z", "2026-07-20T00:00:00Z",
    ]

    # Paging.
    paged = client.get("/api/audit", params={"limit": 1, "offset": 1}).json()
    assert len(paged["entries"]) == 1
    assert paged["entries"][0]["timestamp"] == "2026-07-21T00:00:00Z"

    # Tamper one row's sealed hash directly — the chain must now report broken, not silently
    # re-verify around the corruption.
    row = session.query(AuditLog).filter_by(timestamp="2026-07-20T00:00:00Z").one()
    row.this_hash = "0" * 64
    session.commit()

    tampered = client.get("/api/audit").json()
    assert tampered["chain_intact"] is False
