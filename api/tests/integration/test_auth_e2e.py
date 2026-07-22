"""AUTH-CONSOLIDATE — authentication proven through the REAL app, over REAL HTTP.

Every test here drives ``fastapi.testclient.TestClient`` against ``app.main.app`` (the same
object uvicorn serves) and asserts the REAL status code. Nothing here asserts against an
invented ``request.state`` contract; nothing here calls a verification function directly.

THE TEST THAT EXISTS BECAUSE OF THE LAST ROUND: a reviewer inserted
``return Principal(user_id="attacker", org_id="any-org", role=Role.OWNER, email="e@e.com")`` as
the first statement of ``get_principal`` and the whole suite stayed green.
:func:`test_valid_token_returns_the_tokens_own_principal` and
:func:`test_forged_principal_cannot_be_smuggled_in` both fail on that mutation, because they
assert the response carries the identity from THIS request's token — an identity the mutation
cannot know.

A real Ed25519 keypair is served from a real localhost JWKS endpoint (``http.server``); no
network, no mocks of the thing under test.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Must be set before importing app.main (the module builds the app at import time).
os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app.core import betterauth  # noqa: E402
from app.core.principal import current_org  # noqa: E402
from app.main import app  # noqa: E402


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class _JWKSHandler(BaseHTTPRequestHandler):
    jwks_body: bytes = b'{"keys": []}'

    def do_GET(self) -> None:  # noqa: N802 (stdlib method name)
        body = self.jwks_body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 silence access log
        pass


@pytest.fixture
def auth_server(monkeypatch):
    """A real JWKS endpoint on localhost, wired into the app the way production is: via the
    ``MAISHA_BETTER_AUTH_*`` env vars the middleware reads per-request.

    ``kid`` is UNIQUE PER FIXTURE INSTANCE and the listening socket is closed properly — see
    ``test_betterauth.py`` for why (the order-dependent-failure root cause).
    """
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"e2e-kid-{uuid.uuid4()}"
    jwk = {
        "kty": "OKP", "crv": "Ed25519", "x": _b64u(pub_bytes), "kid": kid, "use": "sig",
        "alg": "EdDSA",
    }
    handler_cls = type(
        "_Handler", (_JWKSHandler,), {"jwks_body": json.dumps({"keys": [jwk]}).encode()}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    betterauth._jwks_client.cache_clear()
    # Better Auth defaults issuer and audience to the base URL; keep the app on those defaults.
    monkeypatch.setenv("MAISHA_BETTER_AUTH_URL", base_url)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_AUDIENCE", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_MFA_CLAIM", raising=False)
    # Better Auth only: the legacy shared password must not be able to answer for these tests.
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "0")
    try:
        yield SimpleNamespace(base_url=base_url, kid=kid, priv_pem=priv_pem)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()


def _token(auth_server, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "user-42",
        "email": "cfo@example.com",
        "iss": auth_server.base_url,
        "aud": auth_server.base_url,
        "iat": now,
        "exp": now + 900,
        "activeOrganizationId": "org-7",
        "role": "owner",
    }
    claims.update(overrides)
    for key in [k for k, v in claims.items() if v is _ABSENT]:
        del claims[key]
    return jwt.encode(
        claims, auth_server.priv_pem, algorithm="EdDSA", headers={"kid": auth_server.kid}
    )


_ABSENT = object()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------------------
# Unauthenticated -> 401. Never 200, never a redirect to a password form.
# ---------------------------------------------------------------------------------------


def test_no_token_is_401(auth_server, client):
    assert client.get("/me").status_code == 401
    assert client.get("/").status_code == 401
    assert client.get("/d/gst").status_code == 401


def test_public_allowlist_still_open(auth_server, client):
    """/health must stay reachable for liveness probes — the one deliberate hole."""
    assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------------------
# Bad tokens -> 401, every flavour, through the real app.
# ---------------------------------------------------------------------------------------


def test_malformed_token_is_401(auth_server, client):
    assert client.get("/me", headers=_bearer("not-a-jwt")).status_code == 401
    assert client.get("/me", headers=_bearer("a.b.c")).status_code == 401
    assert client.get("/me", headers=_bearer("")).status_code == 401


def test_expired_token_is_401(auth_server, client):
    now = int(time.time())
    token = _token(auth_server, iat=now - 5000, exp=now - 100)
    assert client.get("/me", headers=_bearer(token)).status_code == 401


def test_wrong_signing_key_is_401(auth_server, client):
    """Signed by an attacker's key, but announcing the REAL published kid."""
    attacker_pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    forged = jwt.encode(
        {
            "sub": "attacker", "email": "e@e.com", "iss": auth_server.base_url,
            "aud": auth_server.base_url, "exp": int(time.time()) + 900,
            "activeOrganizationId": "org-7", "role": "owner",
        },
        attacker_pem,
        algorithm="EdDSA",
        headers={"kid": auth_server.kid},
    )
    assert client.get("/me", headers=_bearer(forged)).status_code == 401


def test_alg_none_is_401(auth_server, client):
    token = jwt.encode(
        {
            "sub": "attacker", "email": "e@e.com", "iss": auth_server.base_url,
            "aud": auth_server.base_url, "exp": int(time.time()) + 900,
            "activeOrganizationId": "org-7", "role": "owner",
        },
        key=None,
        algorithm="none",
        headers={"kid": auth_server.kid},
    )
    assert client.get("/me", headers=_bearer(token)).status_code == 401


def test_wrong_issuer_and_audience_are_401(auth_server, client):
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, iss="https://evil.example.com"))
    ).status_code == 401
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, aud="https://evil.example.com"))
    ).status_code == 401


# ---------------------------------------------------------------------------------------
# Valid token -> 200 AND the right Principal. (Kills the "return attacker Principal" mutation.)
# ---------------------------------------------------------------------------------------


def test_valid_token_returns_the_tokens_own_principal(auth_server, client):
    resp = client.get("/me", headers=_bearer(_token(auth_server)))
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": "user-42",
        "org_id": "org-7",
        "role": "owner",
        "email": "cfo@example.com",
    }


def test_forged_principal_cannot_be_smuggled_in(auth_server, client):
    """Two DIFFERENT valid tokens must yield two different identities on the same app instance.

    A hard-coded/cached/attacker Principal anywhere in the chain makes these two responses
    equal, and this fails.
    """
    a = client.get("/me", headers=_bearer(_token(auth_server))).json()
    b = client.get(
        "/me",
        headers=_bearer(
            _token(
                auth_server, sub="user-99", email="ca@example.com",
                activeOrganizationId="org-42", role="ca",
            )
        ),
    ).json()
    assert a["user_id"] == "user-42" and a["org_id"] == "org-7" and a["role"] == "owner"
    assert b["user_id"] == "user-99" and b["org_id"] == "org-42" and b["role"] == "ca"
    assert a != b


def test_role_claim_maps_and_body_cannot_override_it(auth_server, client):
    """§0.8: the role is the token's. A request body claiming otherwise changes nothing."""
    token = _token(auth_server, role="investor", sub="inv-1", email="lp@example.com")
    resp = client.get(
        "/me", headers=_bearer(token), params={"role": "owner", "org_id": "org-victim"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "investor"
    assert resp.json()["org_id"] == "org-7"


# ---------------------------------------------------------------------------------------
# Verified but unauthorized -> 403, and NEVER a defaulted org.
# ---------------------------------------------------------------------------------------


def test_missing_org_yields_403_never_a_default_org(auth_server, client):
    resp = client.get("/me", headers=_bearer(_token(auth_server, activeOrganizationId=_ABSENT)))
    assert resp.status_code == 403
    assert "org-7" not in resp.text  # no leak of any org, defaulted or otherwise


def test_unmapped_role_is_403_not_downgraded(auth_server, client):
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, role="galactic-emperor"))
    ).status_code == 403
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, role=_ABSENT))
    ).status_code == 403


# ---------------------------------------------------------------------------------------
# Fail closed: the bearer path never degrades into the legacy path.
# ---------------------------------------------------------------------------------------


def test_bad_token_does_not_fall_back_to_a_valid_legacy_cookie(auth_server, client, monkeypatch):
    """THE fail-open a reviewer would hunt for: hold a perfectly good legacy session cookie AND
    present a bad bearer token. The bad token must lose. 401, not 200."""
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "1")
    assert client.post("/login", data={"password": "change-me"}).status_code in (200, 303)
    assert client.get("/").status_code == 200  # the cookie alone works (legacy dev login)
    assert client.get("/", headers=_bearer("not-a-jwt")).status_code == 401
    assert client.get("/", headers=_bearer(_token(auth_server, exp=1))).status_code == 401


def test_legacy_cookie_session_has_no_principal_and_no_org(auth_server, client, monkeypatch):
    """The legacy dev login authenticates but carries no identity: /me must refuse it rather
    than invent one, and it must not bind any org for RLS."""
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "1")
    client.post("/login", data={"password": "change-me"})
    assert client.get("/me").status_code == 401


def test_legacy_login_disabled_returns_404_not_a_cookie(auth_server, client):
    """With legacy off (its production state), POST /login must not mint a cookie at all."""
    resp = client.post("/login", data={"password": "change-me"})
    assert resp.status_code == 404
    assert not resp.cookies


def test_unreachable_jwks_is_401_never_accepted_unverified(auth_server, client, monkeypatch):
    token = _token(auth_server)
    monkeypatch.setenv("MAISHA_BETTER_AUTH_URL", "http://127.0.0.1:1")  # nothing listens on :1
    betterauth._jwks_client.cache_clear()
    assert client.get("/me", headers=_bearer(token)).status_code == 401


def test_better_auth_unconfigured_is_401_not_open(auth_server, client, monkeypatch):
    token = _token(auth_server)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_URL", raising=False)
    assert client.get("/me", headers=_bearer(token)).status_code == 401


# ---------------------------------------------------------------------------------------
# §0.8 RLS: the verified org, and only it, reaches the database connection.
# ---------------------------------------------------------------------------------------


def test_verified_org_is_bound_to_the_db_connection(auth_server, client, monkeypatch):
    """Drive a DB-touching route with a real token and capture what the connection-checkout
    listener actually saw. Proves the org travels from the TOKEN to the RLS session GUC."""
    import app.main as main

    seen: list[str | None] = []

    def _spy(dbapi_conn, dialect_name):
        seen.append(current_org())
        return False

    monkeypatch.setattr(main, "bind_org_guc", _spy)

    assert client.get("/", headers=_bearer(_token(auth_server))).status_code == 200
    assert seen, "connection checkout listener never fired — RLS binding is not wired"
    assert set(seen) == {"org-7"}

    seen.clear()
    other = _token(auth_server, sub="user-99", activeOrganizationId="org-42", role="admin")
    assert client.get("/", headers=_bearer(other)).status_code == 200
    assert set(seen) == {"org-42"}, "a pooled connection kept the previous request's org"


def test_no_org_is_bound_for_an_unauthenticated_legacy_session(auth_server, client, monkeypatch):
    """Fail-closed: the legacy cookie path binds NO org, so RLS matches no rows."""
    import app.main as main

    seen: list[str | None] = []
    monkeypatch.setattr(main, "bind_org_guc", lambda c, d: seen.append(current_org()) or False)
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "1")
    client.post("/login", data={"password": "change-me"})

    assert client.get("/").status_code == 200
    assert seen and set(seen) == {None}


def test_org_context_does_not_leak_after_the_request(auth_server, client):
    assert client.get("/me", headers=_bearer(_token(auth_server))).status_code == 200
    assert current_org() is None


# ---------------------------------------------------------------------------------------
# MFA policy ported from the retired identity layer — opt-in, but real when opted in.
# ---------------------------------------------------------------------------------------


def test_mfa_claim_enforced_for_privileged_roles_when_configured(auth_server, client, monkeypatch):
    monkeypatch.setenv("MAISHA_BETTER_AUTH_MFA_CLAIM", "twoFactorEnabled")

    # Owner without the claim -> denied (was mfa_required(OWNER) in app.core.identity).
    assert client.get("/me", headers=_bearer(_token(auth_server))).status_code == 403
    # Owner with it -> allowed.
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, twoFactorEnabled=True))
    ).status_code == 200
    # Non-privileged role is not subject to the policy.
    assert client.get(
        "/me", headers=_bearer(_token(auth_server, role="ca", sub="ca-1"))
    ).status_code == 200


def test_mfa_not_enforced_when_no_claim_is_configured(auth_server, client):
    """Honest default: unconfigured means NOT enforced, and the tests say so out loud."""
    assert client.get("/me", headers=_bearer(_token(auth_server))).status_code == 200


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
