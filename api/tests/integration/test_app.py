"""App-level integration: the FastAPI surface renders and reports health. Uses an
in-memory DB; does not require the Mahsa sidecar."""

import os

# Must be set before importing app.main (module instantiates the app at import time).
os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_dashboard_renders_all_domain_cards():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Domain Health" in body
    # every domain appears as a card
    for d in ("treasury", "payroll", "gst", "vault"):
        assert d in body
    # all 12 domains are now implemented -> none render with the "pending" pill
    assert "pill--pending" not in body
    # KPI strip + panels render (degrades without Mahsa)
    assert "Compliance Calendar" in body
    assert "Approvals Pending" in body
    # the Ask Maisha bar is present on every page
    assert 'id="ask-input"' in body


def test_domain_page_renders():
    resp = client.get("/d/gst")
    assert resp.status_code == 200
    body = resp.text
    assert "Figures" in body
    assert "gst" in body.lower()


def test_unknown_domain_404():
    assert client.get("/d/not-a-domain").status_code == 404


def test_ask_page_empty_shows_suggestions():
    resp = client.get("/ask")
    assert resp.status_code == 200
    assert "Try asking" in resp.text


def test_ask_page_with_query_degrades_to_facts():
    # No Mahsa, LLM off -> deterministic figures, flagged offline.
    resp = client.get("/ask", params={"q": "what's our runway?"})
    assert resp.status_code == 200
    body = resp.text
    assert "deterministic figures" in body
    assert "treasury" in body.lower()


def test_ask_post_returns_answer_card():
    resp = client.post("/ask", data={"q": "any MSME payments overdue?"})
    assert resp.status_code == 200
    body = resp.text
    assert "answer__prov" in body  # the answer-card partial rendered
    assert "payables" in body.lower()
