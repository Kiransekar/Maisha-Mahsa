"""SPEC-MEMCITE-1.0 MEM.P0-2 — /api/memory + /api/playbook/{id}/feedback over HTTP, including
the cross-org RED-TEAM read: a verified org-B caller must receive NONE of org A's memory
bytes through any read surface (byte-level assert, the T11 precedent).

Payload semantics + tenant scoping only — the RBAC gates for these five routes are proven
over real signed tokens in test_rbac_matrix.py (API_ROUTE_GATES rows).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.audit_store import load_chain_for
from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.shared import Org
from app.db.session import get_session
from app.web.api_memory import playbook_router, router

pytestmark = pytest.mark.integration

OWNER_A = Principal(user_id="user-a", org_id="org-a", role=Role.OWNER, email="a@example.com")
OWNER_B = Principal(user_id="user-b", org_id="org-b", role=Role.OWNER, email="b@example.com")


def _client(session: Session, principal: Principal) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(playbook_router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: principal
    return TestClient(app)


def test_memory_lifecycle_put_get_append_history(session):
    session.add(Org(id="org-a", name="Acme Traders Pvt Ltd"))
    session.commit()
    client = _client(session, OWNER_A)

    put = client.put("/api/memory", json={"content": "- Conservative risk appetite"})
    assert put.status_code == 200, put.text
    assert put.json()["used"] == len("- Conservative risk appetite")
    assert put.json()["limit"] == 2200

    got = client.get("/api/memory")
    assert got.status_code == 200
    body = got.json()
    assert body["cfo"]["content"] == "- Conservative risk appetite"
    # live-rendered org profile + the verbatim context-only label (§0.4 made visible)
    assert "Acme Traders Pvt Ltd" in body["profile"]
    assert "NEVER a source of numbers" in body["profile"]

    appended = client.post("/api/memory/append", json={"line": "Prefer old regime"})
    assert appended.status_code == 200
    assert appended.json()["content"].endswith("- Prefer old regime")

    history = client.get("/api/memory/history")
    assert history.status_code == 200
    trail = history.json()["history"]
    assert [h["content"] for h in trail] == ["- Conservative risk appetite"]
    assert trail[0]["superseded_by"] == "user-a"
    assert trail[0]["audit_seq"] is not None


def test_overflow_is_a_422_with_the_verbatim_reject_message(session):
    client = _client(session, OWNER_A)
    client.put("/api/memory", json={"content": "- keep me"})

    big = "\n".join(f"- durable fact number {i:04d} about the company posture" for i in range(60))
    resp = client.put("/api/memory", json={"content": big})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "chars after consolidation; the limit is 2200" in detail
    assert "Remove or shorten a line to make room (durable facts only)." in detail
    # rejected, not truncated: the stored block is untouched
    assert client.get("/api/memory").json()["cfo"]["content"] == "- keep me"


def test_red_team_cross_org_read_returns_none_of_org_a_bytes(session):
    """Org A writes a posture; a VERIFIED org-B principal reads every surface and must get
    empty blocks with zero org-A bytes anywhere in the response bodies. App-level scoping is
    Principal-only (§A3); on Postgres, RLS in migration 0011 enforces the same below the app.
    """
    session.add(Org(id="org-a", name="Acme Traders Pvt Ltd"))
    session.commit()
    secret = "Never disclose: acquisition talks with Bharat Foods"
    a = _client(session, OWNER_A)
    assert a.put("/api/memory", json={"content": f"- {secret}"}).status_code == 200
    assert a.put("/api/memory", json={"content": "- v2 posture"}).status_code == 200  # history row

    b = _client(session, OWNER_B)
    got = b.get("/api/memory")
    assert got.status_code == 200
    assert got.json()["cfo"]["content"] == ""
    assert got.json()["profile"] == ""  # org A's name does not render for B either
    history = b.get("/api/memory/history")
    assert history.status_code == 200
    assert history.json()["history"] == []
    # BYTE-LEVEL: no org-A memory content, and no org-A org name, in any of B's responses.
    for resp in (got, history):
        assert secret not in resp.text
        assert "Acme" not in resp.text

    # and B's own write lands in B's org only — A's block is untouched by it
    assert b.put("/api/memory", json={"content": "- org B posture"}).status_code == 200
    assert a.get("/api/memory").json()["cfo"]["content"] == "- v2 posture"


def test_playbook_feedback_route_upserts_seals_and_404s_unknown_ids(session):
    client = _client(session, OWNER_A)

    ok = client.post("/api/playbook/GST-LATEFEE/feedback", json={"verdict": "dismissed"})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"playbook_id": "GST-LATEFEE", "verdict": "dismissed"}
    # sealed onto org A's OWN chain, attributed to the verified caller
    chain = load_chain_for(session, "org-a")
    assert [e.action for e in chain] == ["playbook.dismissed"]
    assert chain[0].user_id == "user-a"

    bad_verdict = client.post("/api/playbook/GST-LATEFEE/feedback", json={"verdict": "meh"})
    assert bad_verdict.status_code == 422  # Literal-typed body, refused before the service

    unknown = client.post("/api/playbook/NO-SUCH/feedback", json={"verdict": "adopted"})
    assert unknown.status_code == 404
    assert "unknown playbook" in unknown.json()["detail"]
    assert len(load_chain_for(session, "org-a")) == 1  # nothing further sealed
