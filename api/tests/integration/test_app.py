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
