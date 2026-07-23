"""P2-6 (hmac-retire): the HTMX surface authenticates with the SAME Better Auth JWT as the SPA.

The legacy HMAC-cookie password login is DELETED. These tests drive the real app the way an
HTMX browser does: the JWT rides in the ``maisha_jwt`` cookie, verified through the one JWKS
path (``app.core.betterauth``). The bearer-header path and every token-rejection mode are
proven in test_auth_e2e.py; this file pins the cookie/HTMX surface and the sign-in redirect.
"""

import os
import time

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.betterauth import TOKEN_COOKIE  # noqa: E402
from app.main import app  # noqa: E402

HTML = {"accept": "text/html"}


def _mint(env, **overrides) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "u-owner",
        "email": "owner@example.com",
        "iss": env.base_url,
        "aud": env.base_url,
        "iat": now,
        "exp": now + 900,
        "activeOrganizationId": "org-7",
        "role": "owner",
    }
    claims.update(overrides)
    return jwt.encode(claims, env.priv_pem, algorithm="EdDSA", headers={"kid": env.kid})


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_is_public(betterauth_owner_env, client):
    assert client.get("/health", follow_redirects=False).status_code == 200


def test_login_redirects_to_the_sign_in_page(betterauth_owner_env, client):
    """/login is no longer a password form — it hands the browser to Better Auth sign-in."""
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/sign-in"


def test_password_login_endpoint_is_gone(betterauth_owner_env, client):
    """POST /login (the HMAC flow) no longer exists and can never mint a session."""
    r = client.post("/login", data={"password": "change-me"}, follow_redirects=False)
    assert r.status_code == 405  # GET-only redirect route; the form handler is deleted
    assert not r.cookies


def test_unauthenticated_browser_is_redirected_to_login(betterauth_owner_env, client):
    r = client.get("/", headers=HTML, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_unauthenticated_api_request_is_401(betterauth_owner_env, client):
    assert client.get("/", follow_redirects=False).status_code == 401


def test_cookie_jwt_authenticates_the_htmx_surface(betterauth_owner_env, client):
    """The whole point of the migration: the SPA's JWT, carried in a cookie, opens the HTMX
    pages AND yields the token's own principal (not an invented one)."""
    client.cookies.set(TOKEN_COOKIE, betterauth_owner_env.token)
    assert client.get("/", headers=HTML, follow_redirects=False).status_code == 200
    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["user_id"] == "u-owner"
    assert me.json()["org_id"] == "org-7"


def test_bad_cookie_jwt_browser_is_redirected_and_cookie_cleared(betterauth_owner_env, client):
    client.cookies.set(TOKEN_COOKIE, "not-a-jwt")
    r = client.get("/", headers=HTML, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")
    # the bad cookie is deleted so the browser doesn't redirect-loop after signing in again
    assert f'{TOKEN_COOKIE}=""' in r.headers.get("set-cookie", "")


def test_bad_cookie_jwt_api_request_is_401_not_anonymous(betterauth_owner_env, client):
    client.cookies.set(TOKEN_COOKIE, "not-a-jwt")
    assert client.get("/me", follow_redirects=False).status_code == 401
    expired = _mint(betterauth_owner_env, iat=int(time.time()) - 5000, exp=int(time.time()) - 100)
    client.cookies.set(TOKEN_COOKIE, expired)
    assert client.get("/me", follow_redirects=False).status_code == 401


def test_logout_clears_the_jwt_cookie(betterauth_owner_env, client):
    client.cookies.set(TOKEN_COOKIE, betterauth_owner_env.token)
    assert client.get("/", headers=HTML, follow_redirects=False).status_code == 200
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    # the response instructs the browser to drop the JWT cookie (httpx's jar can't be evicted
    # cross-domain in tests, so assert the header a real browser honours)
    set_cookie = r.headers.get("set-cookie", "")
    assert f'{TOKEN_COOKIE}=""' in set_cookie and "expires" in set_cookie.lower()
    client.cookies.delete(TOKEN_COOKIE)  # what that header does in a browser
    assert client.get("/", headers=HTML, follow_redirects=False).status_code == 303


def test_production_refuses_to_boot_without_better_auth(monkeypatch):
    """P1-SECRETS successor: production with no Better Auth URL fails at boot, loudly."""
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("MAISHA_ENVIRONMENT", "production")
    monkeypatch.delenv("MAISHA_BETTER_AUTH_URL", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="MAISHA_BETTER_AUTH_URL"):
            create_app()
        # configured URL but the shipped default preview-token secret -> still refused
        monkeypatch.setenv("MAISHA_BETTER_AUTH_URL", "https://auth.example.com")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="MAISHA_SESSION_SECRET"):
            create_app()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
