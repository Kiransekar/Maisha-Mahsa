"""P1-1 — POST /api/ask (the SPA twin of the HTMX /ask page) against the REAL Mahsa binary.

What is actually pinned here (not shape-checking):
  1. Same pipeline as the HTMX page (``app.core.ask.answer_query``, verbatim) — a routable
     query returns fact-backed figures, each with a real tri-state (never a hardcoded
     "verified"; app.core.mahsa_coverage decides that per §0.4).
  2. An unroutable query abstains honestly (empty figures, no fabricated domain).
  3. RBAC: the route is gated ``read`` only — proven here with a real denied role (Investor,
     who does not hold ``read``); the full role x route matrix lives in
     test_rbac_matrix.py (this file adds POST /api/ask's row there).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.mahsa_client import MahsaClient
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.session import get_session
from app.deps import get_mahsa
from app.web.api_domains import router

pytestmark = pytest.mark.integration


def _client(session: Session, mahsa_url: str, role: Role = Role.OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_url)
    # Same seam as test_api_domains.py: the one auth dependency is overridden with a real
    # Principal of the role under test; the matrix itself runs over real signed tokens in
    # test_rbac_matrix.py.
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-1", org_id="org-7", role=role, email="u@example.com"
    )
    return TestClient(app)


def test_ask_returns_fact_backed_figures_with_honest_verdicts(session, mahsa_server):
    client = _client(session, mahsa_server)

    resp = client.post("/api/ask", json={"q": "what's our runway?"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["domain"] == "treasury"
    assert body["mahsa_up"] is True
    assert body["figures"], "a routable query must surface at least one figure"
    for f in body["figures"]:
        assert set(f) == {"label", "value", "state"}
        assert f["state"] in ("verified", "honest_pending", "unbacked")
    # A plain snapshot fact (not a Mahsa coverage target) is never fabricated verified —
    # same honesty rule as GET /api/domains/{domain}.
    assert any(f["state"] == "honest_pending" for f in body["figures"])
    assert isinstance(body["citations"], list)
    assert body["abstained"] is False


def test_ask_unroutable_query_abstains_without_fabricating_a_domain(session, mahsa_server):
    client = _client(session, mahsa_server)

    resp = client.post("/api/ask", json={"q": "hello there"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["domain"] is None
    assert body["abstained"] is True
    assert body["figures"] == []


def test_ask_states_mahsa_down_never_fabricates(session):
    client = _client(session, "http://127.0.0.1:9")  # nothing listening

    body = client.post("/api/ask", json={"q": "what's our runway?"}).json()
    assert body["mahsa_up"] is False
    # Degraded: deterministic facts only, no Mahsa verdict/status.
    assert body["status"] is None


def test_ask_empty_query_is_a_422_not_a_500(session, mahsa_server):
    client = _client(session, mahsa_server)
    resp = client.post("/api/ask", json={"q": ""})
    assert resp.status_code == 422


def test_tri_state_projection_fails_closed():
    """§0.4: only an explicit verdict earns its state. A blocked verdict — and the impossible
    all-false verdict — must both project to "unbacked", never upgraded by omission. (The
    blocked path can't be reached over HTTP with the LLM off, so it is pinned directly.)"""
    from app.core.verify import FigureVerdict
    from app.web.api_domains import _tri_state

    fv = lambda v, b, hp: FigureVerdict(verified=v, blocked=b, honest_pending=hp)  # noqa: E731
    assert _tri_state(fv(True, False, False)) == "verified"
    assert _tri_state(fv(False, False, True)) == "honest_pending"
    assert _tri_state(fv(False, True, False)) == "unbacked"
    assert _tri_state(fv(False, False, False)) == "unbacked"  # unknown state -> fail closed


def test_ask_denies_a_role_without_read(session, mahsa_server):
    """Investor holds no ``read`` capability (app.core.rbac.ROLE_CAPABILITIES) — the router's
    baseline gate must deny it before ``answer_query`` ever runs."""
    client = _client(session, mahsa_server, role=Role.INVESTOR)
    resp = client.post("/api/ask", json={"q": "what's our runway?"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "missing capability: read"
