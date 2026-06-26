"""P1-AUTH: the single-user login guard protects the app surface."""

import os

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import auth  # noqa: E402
from app.main import app  # noqa: E402


def test_health_is_public():
    c = TestClient(app)
    assert c.get("/health", follow_redirects=False).status_code == 200


def test_login_page_is_public():
    c = TestClient(app)
    assert c.get("/login", follow_redirects=False).status_code == 200


def test_unauthenticated_request_redirects_to_login():
    c = TestClient(app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_wrong_password_rejected():
    c = TestClient(app)
    r = c.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 401
    # still locked out
    assert c.get("/", follow_redirects=False).status_code == 303


def test_login_then_access_granted():
    c = TestClient(app)
    c.post("/login", data={"password": "change-me"})
    assert c.get("/", follow_redirects=False).status_code == 200


def test_logout_clears_session():
    c = TestClient(app)
    c.post("/login", data={"password": "change-me"})
    assert c.get("/", follow_redirects=False).status_code == 200
    c.post("/logout")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_production_refuses_default_secrets():
    with pytest.raises(RuntimeError):
        auth.assert_production_secrets(
            environment="production",
            app_password=auth.DEFAULT_PASSWORD,
            session_secret="strong-secret",
        )
    # non-default secrets boot fine
    auth.assert_production_secrets(
        environment="production", app_password="strong", session_secret="also-strong"
    )
