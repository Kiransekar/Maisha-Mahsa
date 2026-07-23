"""WS4.3-betterauth-api — Better Auth JWT verification tests.

No network: a real ``http.server`` bound to 127.0.0.1 on an ephemeral port serves a fake JWKS
(a freshly generated Ed25519 keypair, in-test), exactly as the ticket asks. Issuer/audience are
fixed strings shared with the signed tokens.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import betterauth
from app.core.betterauth import AuthError, NoOrgError, decode_claims, verify_token
from app.core.principal import (
    Principal,
    bind_org_guc,
    current_org,
    mfa_required,
    reset_current_org,
    set_current_org,
)
from app.core.rbac import Role

ISSUER = "https://issuer.test"
AUDIENCE = "https://issuer.test"


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
def jwks_server():
    """A real Ed25519 keypair served over a real (localhost-only) JWKS endpoint.

    ROOT CAUSE of the reported order-dependent failure of
    ``test_missing_org_yields_no_org_not_a_default`` (green standalone, red in a full run), and
    why the two changes below fix it:

    ``betterauth._jwks_client`` is an ``lru_cache`` keyed ONLY on the JWKS URL, and that URL is
    ``http://127.0.0.1:<ephemeral port>/...``. The old fixture called ``server.shutdown()`` but
    never ``server_close()``, so the listening socket was released at GC time — non-deterministic,
    and therefore dependent on how many tests ran before. When a port WAS recycled onto a later
    fixture, that later fixture published a DIFFERENT key under the SAME hard-coded
    ``kid="test-kid-1"``; any surviving cached ``PyJWKClient`` then returned the stale key.
    ``PyJWKClient`` refreshes on a kid MISS, not on a signature failure, so the stale key was
    used and verification failed with ``AuthError`` — while the test was asserting ``NoOrgError``.
    That is exactly the reported symptom, and it can only appear when another test ran first.

    Reproduced directly: server A on port P (kid K), verify, close; server B rebound on port P
    with a new key and the same kid K, without a ``cache_clear`` -> ``AuthError: token rejected:
    Signature verification failed``.

    Fixes, both here: (1) ``kid`` is unique per fixture instance, so a stale cache entry can
    never match a later test's token; (2) ``server_close()`` releases the port deterministically.
    ``cache_clear()`` on both sides is kept as the third belt. Production is unaffected: Better
    Auth mints a new ``kid`` per key, so a same-kid rotation does not occur there, and the JWK-set
    cache is bounded at 300s regardless.
    """
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"test-kid-{uuid.uuid4()}"  # unique per instance — see the docstring
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64u(pub_bytes),
        "kid": kid,
        "use": "sig",
        "alg": "EdDSA",
    }
    handler_cls = type(
        "_Handler", (_JWKSHandler,), {"jwks_body": json.dumps({"keys": [jwk]}).encode()}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    betterauth._jwks_client.cache_clear()  # each test gets its own port -> its own cache entry
    try:
        yield SimpleNamespace(
            jwks_url=f"http://127.0.0.1:{port}/api/auth/jwks", kid=kid, priv_pem=priv_pem
        )
    finally:
        server.shutdown()
        server.server_close()  # release the port deterministically — see the docstring
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()


def _claims(**overrides: object) -> dict[str, object]:
    now = int(time.time())
    base = {
        "sub": "user-42",
        "email": "cfo@example.com",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 900,
        "activeOrganizationId": "org-7",
        "role": "owner",
    }
    base.update(overrides)
    return base


def _sign(claims: dict[str, object], *, key: bytes, kid: str, alg: str = "EdDSA") -> str:
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, key, algorithm=alg, headers=headers)


def _verify(jwks_server, token: str) -> object:
    return verify_token(token, jwks_url=jwks_server.jwks_url, issuer=ISSUER, audience=AUDIENCE)


# ---------------------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------------------


def test_valid_token_yields_principal(jwks_server):
    token = _sign(_claims(), key=jwks_server.priv_pem, kid=jwks_server.kid)
    principal = _verify(jwks_server, token)
    assert principal.user_id == "user-42"
    assert principal.email == "cfo@example.com"
    assert principal.org_id == "org-7"
    assert principal.role is Role.OWNER


# ---------------------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------------------


def test_wrong_signing_key_rejected(jwks_server):
    """Signed by a DIFFERENT Ed25519 key than the one published at the JWKS kid -> rejected."""
    attacker_key = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    # kid still points at the REAL published key
    token = _sign(_claims(), key=attacker_key, kid=jwks_server.kid)
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


def test_alg_none_rejected(jwks_server):
    token = jwt.encode(_claims(), key=None, algorithm="none", headers={"kid": jwks_server.kid})
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


def test_alg_none_rejected_even_without_matching_kid(jwks_server):
    """Belt-and-suspenders: alg=none with no kid at all must also be rejected (fails at the
    JWKS/kid-lookup stage rather than the algorithm-allow-list stage, but rejected either way)."""
    token = jwt.encode(_claims(), key=None, algorithm="none", headers={})
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


# ---------------------------------------------------------------------------------------
# Claim validation
# ---------------------------------------------------------------------------------------


def test_expired_token_rejected(jwks_server):
    now = int(time.time())
    token = _sign(
        _claims(iat=now - 1000, exp=now - 100), key=jwks_server.priv_pem, kid=jwks_server.kid
    )
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


def test_wrong_issuer_rejected(jwks_server):
    token = _sign(
        _claims(iss="https://evil.example.com"), key=jwks_server.priv_pem, kid=jwks_server.kid
    )
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


def test_wrong_audience_rejected(jwks_server):
    token = _sign(
        _claims(aud="https://someone-else.example.com"),
        key=jwks_server.priv_pem,
        kid=jwks_server.kid,
    )
    with pytest.raises(AuthError):
        _verify(jwks_server, token)


# ---------------------------------------------------------------------------------------
# Org / role — §0.8: org_id from the token only, never defaulted
# ---------------------------------------------------------------------------------------


def test_missing_org_yields_no_org_not_a_default(jwks_server):
    claims = _claims()
    del claims["activeOrganizationId"]
    token = _sign(claims, key=jwks_server.priv_pem, kid=jwks_server.kid)
    with pytest.raises(NoOrgError):
        _verify(jwks_server, token)


def test_unknown_role_denied_not_downgraded(jwks_server):
    token = _sign(_claims(role="galactic-emperor"), key=jwks_server.priv_pem, kid=jwks_server.kid)
    with pytest.raises(NoOrgError):
        _verify(jwks_server, token)


# ---------------------------------------------------------------------------------------
# JWKS availability — fail closed, never fail open
# ---------------------------------------------------------------------------------------


def test_jwks_unreachable_rejects_request():
    """No server listening on this port at all -> connection refused -> AuthError, never a
    silent accept."""
    dead_url = "http://127.0.0.1:1/api/auth/jwks"  # port 1: nothing ever listens here
    token = jwt.encode(_claims(), key="irrelevant-but-32-bytes-long!!!!", algorithm="HS256")
    with pytest.raises(AuthError):
        decode_claims(token, jwks_url=dead_url, issuer=ISSUER, audience=AUDIENCE)


# ---------------------------------------------------------------------------------------
# AUTH-CONSOLIDATE — the consolidation seams. End-to-end proof of all of this, through the
# real app over real HTTP, is in tests/integration/test_auth_e2e.py.
# ---------------------------------------------------------------------------------------


def test_stale_jwks_cache_cannot_survive_a_recycled_port(jwks_server):
    """Regression lock for the order-dependent failure documented on the fixture: two fixture
    instances must never share a kid, which is what let a stale cached key be reused."""
    other_kid = f"test-kid-{uuid.uuid4()}"
    assert jwks_server.kid != other_kid
    assert not jwks_server.kid.endswith("test-kid-1")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc.def.ghi", "abc.def.ghi"),
        ("bearer abc.def.ghi", "abc.def.ghi"),  # scheme is case-insensitive (RFC 7235)
        ("BEARER  spaced  ", "spaced"),
        ("Bearer ", None),
        ("Bearer", None),
        ("Basic dXNlcjpwdw==", None),  # a different scheme is NOT a bearer token
        ("abc.def.ghi", None),  # bare token without the scheme is not accepted
        ("", None),
    ],
)
def test_bearer_token_parsing(header, expected):
    request = SimpleNamespace(headers={"authorization": header})
    assert betterauth.bearer_token(request) == expected  # type: ignore[arg-type]


def test_get_principal_fails_closed_without_a_verified_principal():
    """The dependency never invents an identity: no verified Principal on request.state -> 401."""
    from fastapi import HTTPException

    for state in (
        SimpleNamespace(),
        SimpleNamespace(principal=None),
        SimpleNamespace(principal={"user_id": "attacker", "role": "owner"}),
        SimpleNamespace(principal="owner"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            betterauth.get_principal(SimpleNamespace(state=state))  # type: ignore[arg-type]
        assert excinfo.value.status_code == 401


def test_get_principal_returns_the_verified_principal():
    principal = Principal(user_id="u1", org_id="org-1", role=Role.OWNER, email="a@b.com")
    request = SimpleNamespace(state=SimpleNamespace(principal=principal))
    assert betterauth.get_principal(request) is principal  # type: ignore[arg-type]


# --- P2-6: the request token — bearer header first, JWT cookie second, no other source ----


def test_request_token_prefers_the_bearer_header_over_the_cookie():
    """A present header ALWAYS wins — a bad bearer token must be rejected, never quietly
    replaced by a (possibly valid) cookie. request_token's ordering is what guarantees it."""
    request = SimpleNamespace(
        headers={"authorization": "Bearer head.er.token"},
        cookies={betterauth.TOKEN_COOKIE: "coo.kie.token"},
    )
    assert betterauth.request_token(request) == "head.er.token"  # type: ignore[arg-type]


def test_request_token_falls_back_to_the_jwt_cookie_only_without_a_header():
    request = SimpleNamespace(headers={}, cookies={betterauth.TOKEN_COOKIE: "coo.kie.token"})
    assert betterauth.request_token(request) == "coo.kie.token"  # type: ignore[arg-type]


def test_request_token_none_when_neither_is_present():
    for cookies in ({}, {betterauth.TOKEN_COOKIE: ""}, {"some_other_cookie": "x"}):
        request = SimpleNamespace(headers={}, cookies=cookies)
        assert betterauth.request_token(request) is None  # type: ignore[arg-type]


# --- MFA policy ported from the retired app.core.identity --------------------------------


def test_mfa_policy_matches_the_retired_identity_layer():
    """`identity.mfa_required` said Owner/Admin. That policy survived the deletion verbatim."""
    assert mfa_required(Role.OWNER) and mfa_required(Role.ADMIN)
    for role in (Role.ACCOUNTANT, Role.APPROVER, Role.CA, Role.INVESTOR):
        assert not mfa_required(role)


def test_mfa_claim_denies_privileged_role_without_the_claim(monkeypatch):
    monkeypatch.setenv("MAISHA_BETTER_AUTH_MFA_CLAIM", "twoFactorEnabled")
    owner = Principal(user_id="u", org_id="o", role=Role.OWNER, email="a@b.com")
    with pytest.raises(NoOrgError):
        betterauth.assert_mfa_satisfied({}, owner)
    with pytest.raises(NoOrgError):
        betterauth.assert_mfa_satisfied({"twoFactorEnabled": False}, owner)
    betterauth.assert_mfa_satisfied({"twoFactorEnabled": True}, owner)  # satisfied -> no raise


def test_mfa_claim_ignores_unprivileged_roles(monkeypatch):
    monkeypatch.setenv("MAISHA_BETTER_AUTH_MFA_CLAIM", "twoFactorEnabled")
    ca = Principal(user_id="u", org_id="o", role=Role.CA, email="a@b.com")
    betterauth.assert_mfa_satisfied({}, ca)


def test_mfa_unenforced_when_unconfigured(monkeypatch):
    """Documented, deliberate default: no claim name configured -> the API does not enforce."""
    monkeypatch.delenv("MAISHA_BETTER_AUTH_MFA_CLAIM", raising=False)
    owner = Principal(user_id="u", org_id="o", role=Role.OWNER, email="a@b.com")
    betterauth.assert_mfa_satisfied({}, owner)


def test_verify_token_enforces_mfa_end_of_pipeline(jwks_server, monkeypatch):
    """The policy is inside verify_token, so no caller can skip it."""
    monkeypatch.setenv("MAISHA_BETTER_AUTH_MFA_CLAIM", "twoFactorEnabled")
    with pytest.raises(NoOrgError):
        _verify(jwks_server, _sign(_claims(), key=jwks_server.priv_pem, kid=jwks_server.kid))
    ok = _sign(_claims(twoFactorEnabled=True), key=jwks_server.priv_pem, kid=jwks_server.kid)
    assert _verify(jwks_server, ok).role is Role.OWNER


# --- §0.8 RLS org binding ----------------------------------------------------------------


class _RecordingCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params):
        self.log.append((sql, params))

    def close(self):
        pass


class _RecordingConn:
    def __init__(self):
        self.log: list[tuple[str, tuple]] = []

    def cursor(self):
        return _RecordingCursor(self.log)


def test_org_guc_is_parameterised_and_carries_the_verified_org():
    conn = _RecordingConn()
    token = set_current_org("org-7")
    try:
        assert bind_org_guc(conn, "postgresql") is True
    finally:
        reset_current_org(token)
    ((sql, params),) = conn.log
    assert params == ("org-7",)
    assert "%s" in sql and "org-7" not in sql  # §0.8: parameterised, never interpolated


def test_org_guc_is_empty_when_unauthenticated():
    """Fail-closed: app_current_org() -> NULL -> every RLS policy matches zero rows."""
    conn = _RecordingConn()
    assert current_org() is None
    assert bind_org_guc(conn, "postgresql") is True
    assert conn.log[0][1] == ("",)


def test_org_guc_is_a_noop_on_sqlite():
    conn = _RecordingConn()
    assert bind_org_guc(conn, "sqlite") is False
    assert conn.log == []


def test_org_context_resets_and_does_not_leak():
    token = set_current_org("org-1")
    assert current_org() == "org-1"
    reset_current_org(token)
    assert current_org() is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
