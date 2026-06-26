"""P6 hardening: body-size limit, friendly errors, dependency-aware health, audit-verify."""

import os

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app.jobs import run_audit_verify  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
client.post("/login", data={"password": "change-me"})


def test_oversized_body_rejected_413():
    # Content-Length over the 10 MB cap -> 413 before the body is processed.
    big = b"x" * 11 * 1024 * 1024
    resp = client.post(
        "/ask", content=big,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 413


def test_health_reports_dependencies():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["db"] == "ok"
    # Mahsa isn't running in tests -> reported down, not a crash
    assert body["dependencies"]["mahsa"] == "down"


def test_404_returns_friendly_html_when_browser():
    resp = client.get("/d/not-a-domain", headers={"accept": "text/html"})
    assert resp.status_code == 404
    assert "Page not found" in resp.text


def test_audit_verify_endpoint_reports_intact():
    resp = client.get("/audit/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intact"] is True  # empty/clean chain verifies
    assert "entries" in body


def test_run_audit_verify_job_clean_chain(session):
    result = run_audit_verify(session)
    assert result == {"job": "audit_verify", "intact": True, "entries": 0}
