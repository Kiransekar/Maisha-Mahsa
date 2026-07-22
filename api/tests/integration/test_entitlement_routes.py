"""ENTITLEMENT-ENFORCE — entitlements proven through the REAL app, over REAL HTTP.

Every test drives ``fastapi.testclient.TestClient`` against ``app.main.app`` (the object
uvicorn serves) with a REAL Ed25519-signed Better Auth JWT verified against a REAL localhost
JWKS endpoint, and asserts the REAL status code. Nothing here asserts against an invented
``request.state`` contract, and nothing calls ``guard()`` directly.

What each test kills:
  * ``test_unentitled_tenant_gets_402_*`` — deleting the ``require_feature`` dependency from
    the route, or the ``if not decision.allowed: raise`` in ``_dep``.
  * ``test_entitled_tenant_gets_200_*``   — a gate that denies everyone.
  * ``test_plan_comes_from_the_token_*``  — a hardcoded plan; the SAME route, SAME app, TWO
    tokens, TWO outcomes. A constant cannot satisfy both.
  * ``test_body_claiming_a_higher_plan_is_ignored`` — §0.8, plan from a request field.
  * ``test_statutory_filing_is_never_blocked`` — the load-bearing grace override.
  * ``test_unregistered_key_raises_at_definition_time`` — the cardinal defect: an invented key
    returning a plausible 402.
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
from app.core.entitlement_deps import require_feature, require_quantity  # noqa: E402
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

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def auth_server(monkeypatch):
    """A real JWKS endpoint on localhost, wired into the app exactly as production is."""
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"ent-kid-{uuid.uuid4()}"
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
    monkeypatch.setenv("MAISHA_BETTER_AUTH_URL", base_url)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_AUDIENCE", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_MFA_CLAIM", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_PLAN_CLAIM", raising=False)
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "0")
    try:
        yield SimpleNamespace(base_url=base_url, kid=kid, priv_pem=priv_pem)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()


def _token(auth_server, *, plan: str | None = "basics", org: str = "org-7", **overrides) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "user-42",
        "email": "cfo@example.com",
        "iss": auth_server.base_url,
        "aud": auth_server.base_url,
        "iat": now,
        "exp": now + 900,
        "activeOrganizationId": org,
        "role": "owner",
    }
    if plan is not None:
        claims["plan"] = plan
    claims.update(overrides)
    return jwt.encode(
        claims, auth_server.priv_pem, algorithm="EdDSA", headers={"kid": auth_server.kid}
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- the cardinal defect: an unregistered key must never become a paywall ---------------


def test_unregistered_key_raises_at_definition_time():
    """require_feature('totally_made_up') used to return a plausible 402. Now it cannot exist."""
    with pytest.raises(ValueError, match="FEATURE_REGISTRY"):
        require_feature("totally_made_up")


def test_typo_of_a_real_key_raises_and_names_the_real_one():
    with pytest.raises(ValueError) as exc:
        require_feature("gstr3B")  # real key is "gstr3b"
    assert "gstr3b" in str(exc.value)


def test_registered_key_is_accepted():
    assert require_feature("cap_table") is not None  # the negative tests aren't vacuous


def test_unknown_quantity_kind_raises_at_definition_time():
    with pytest.raises(ValueError, match="unknown quantity gate"):
        require_quantity("hedcount", current=lambda _ctx: 1)


# --- both directions, real HTTP ---------------------------------------------------------
# /api/equity/cap-table is gated on "cap_table", which plans.yaml puts in startup_adds:
# basics -> locked, startup/growth -> entitled.


def test_unentitled_tenant_gets_402_with_reason_and_upgrade_target(auth_server, client):
    resp = client.get("/api/equity/cap-table", headers=_bearer(_token(auth_server, plan="basics")))
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail["error"] == "feature_locked"
    assert detail["feature"] == "cap_table"
    assert detail["plan"] == "basics"
    # WS6.2: locked is VISIBLE — the reason and the upgrade target are in the body.
    assert detail["upsell"] == "startup"
    assert "Startup" in detail["reason"]


def test_entitled_tenant_gets_200_on_the_same_route(auth_server, client):
    resp = client.get("/api/equity/cap-table", headers=_bearer(_token(auth_server, plan="startup")))
    assert resp.status_code == 200


def test_plan_comes_from_the_token_not_a_constant(auth_server, client):
    """SAME app, SAME route, TWO tokens, TWO outcomes. Kills any hardcoded plan."""
    basics = client.get(
        "/api/equity/cap-table", headers=_bearer(_token(auth_server, plan="basics"))
    )
    growth = client.get(
        "/api/equity/cap-table", headers=_bearer(_token(auth_server, plan="growth"))
    )
    assert (basics.status_code, growth.status_code) == (402, 200)


def test_missing_plan_claim_falls_back_to_the_least_privileged_tier(auth_server, client):
    """No plan claim -> orgs.plan's schema default 'basics' -> locked, never wide open."""
    resp = client.get("/api/equity/cap-table", headers=_bearer(_token(auth_server, plan=None)))
    assert resp.status_code == 402
    assert resp.json()["detail"]["plan"] == "basics"


def test_unknown_plan_value_falls_back_to_the_least_privileged_tier(auth_server, client):
    resp = client.get(
        "/api/equity/cap-table", headers=_bearer(_token(auth_server, plan="enterprise-mega"))
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["plan"] == "basics"


def test_body_claiming_a_higher_plan_is_ignored(auth_server, client):
    """§0.8: the plan is a verified token claim; a request field can never raise it."""
    resp = client.post(
        "/api/equity/safe/convert",
        headers=_bearer(_token(auth_server, plan="basics")),
        json={"org_plan": "growth", "investment_amount": 100000000, "valuation_cap": 1000000000,
              "discount_rate": 0.2, "pre_money_valuation": 2000000000,
              "pre_round_shares": 1000000},
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["plan"] == "basics"


def test_gated_route_without_a_token_is_401(auth_server, client):
    assert client.get("/api/equity/cap-table").status_code == 401


def test_gated_route_with_a_bad_token_is_401(auth_server, client):
    assert client.get("/api/equity/cap-table", headers=_bearer("not-a-jwt")).status_code == 401


# --- THE LOAD-BEARING BEHAVIOUR: a statutory filing is never blocked --------------------
# /api/payroll/lwf is gated on "lwf", which is BOTH a startup_adds feature AND a member of
# entitlements.STATUTORY_GRACE_FEATURES. A basics tenant is over the entitlement limit for it
# and MUST still get through.


def test_statutory_filing_is_never_blocked_for_an_unentitled_tenant(auth_server, client, caplog):
    with caplog.at_level("INFO", logger="maisha.entitlements"):
        resp = client.get(
            "/api/payroll/lwf",
            params={"period": "2026-06"},
            headers=_bearer(_token(auth_server, plan="basics")),
        )
    assert resp.status_code == 200, "a statutory filing must never be paywalled"
    ent = resp.json()["entitlement"]
    # ... and the upsell is recorded AFTER the fact, not as a block before it.
    assert ent["grace"] is True
    assert ent["plan"] == "basics"
    assert ent["upsell"] == "startup"
    assert "never blocked" in ent["reason"]
    assert any("entitlement.statutory_grace" in r.message for r in caplog.records)


def test_statutory_filing_for_an_entitled_tenant_is_not_flagged_as_grace(auth_server, client):
    resp = client.get(
        "/api/payroll/lwf",
        params={"period": "2026-06"},
        headers=_bearer(_token(auth_server, plan="startup")),
    )
    assert resp.status_code == 200
    ent = resp.json()["entitlement"]
    assert ent["grace"] is False and ent["upsell"] is None


def test_a_basics_feature_on_the_payroll_router_passes_for_a_basics_tenant(auth_server, client):
    """The gate is not denying indiscriminately: /preview is gated on "salary_structure",
    a Basics feature, so a Basics tenant gets through.

    Read-only on purpose. Every test module shares one in-memory SQLite engine (app.main is
    imported once per process), so a test that POSTs a payroll run leaks rows into other
    modules' fixtures — observed as order-dependent failures in tests/integration/
    test_rbac_matrix.py. Nothing in this file mutates the shared DB.
    """
    resp = client.get(
        "/api/payroll/preview",
        params={"basic": 5000000, "hra": 2000000},
        headers=_bearer(_token(auth_server, plan="basics")),
    )
    assert resp.status_code == 200
