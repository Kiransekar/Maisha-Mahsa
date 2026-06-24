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


def test_action_bar_appears_on_domain_with_actions():
    body = client.get("/d/ledger").text
    assert "Create account" in body  # action bar rendered


def test_action_form_renders():
    resp = client.get("/d/ledger/action/create-account/form")
    assert resp.status_code == 200
    assert 'name="code"' in resp.text


def test_action_submit_persists_and_refreshes():
    resp = client.post(
        "/d/vault/action/ingest",
        data={"file_name": "msa.pdf", "content": "acme agreement", "upload_date": "2026-05-10"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "ingested" in body  # success message / toast
    assert 'id="figures"' in body  # out-of-band figures refresh included


def test_action_submit_bad_input_re_renders_form_with_error():
    # shares_held must be an int; a non-numeric value should re-render the form with an error.
    resp = client.post(
        "/d/equity/action/add-shareholder",
        data={"name": "X", "category": "founder", "shares_held": "not-a-number"},
    )
    assert resp.status_code == 200
    assert "drawer__err" in resp.text


def test_unknown_action_404():
    assert client.get("/d/ledger/action/nope/form").status_code == 404


def test_approvals_page_renders():
    resp = client.get("/approvals")
    assert resp.status_code == 200
    assert "Approvals" in resp.text
    # Mahsa is down in tests -> degraded message, page still renders
    assert "Mahsa sidecar offline" in resp.text


def test_approvals_decide_degrades_without_mahsa():
    resp = client.post("/approvals/gst/decide", data={"decision": "approved"})
    assert resp.status_code == 200
    assert "Mahsa offline" in resp.text  # decision not recorded, surfaced honestly


def test_cfo_page_renders():
    resp = client.get("/cfo")
    assert resp.status_code == 200
    body = resp.text
    assert "CFO Strategy" in body
    assert "Scenario engine" in body
    assert "Cap table" in body


def test_cfo_scenario_returns_result():
    resp = client.post("/cfo/scenario", data={"revenue_mult": "1.2", "extra_cost": "0"})
    assert resp.status_code == 200
    assert "Runway" in resp.text


def test_cfo_investor_send_degrades_without_smtp():
    resp = client.post("/cfo/investor/send", data={})
    assert resp.status_code == 200
    # MailHog isn't running in tests -> surfaced, not raised
    assert "Could not send" in resp.text or "sent to" in resp.text


def test_audit_page_renders_and_verifies_chain():
    resp = client.get("/audit")
    assert resp.status_code == 200
    body = resp.text
    assert "Audit &amp; Trace" in body
    assert "CHAIN INTACT" in body  # empty/clean chain verifies
    assert "LLM trace" in body
