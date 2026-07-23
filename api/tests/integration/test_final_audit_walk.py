"""FINAL-AUDIT probe: seed the demo tenant, then walk every parameter-free GET route (plus the
seeded parameterized ones) as EVERY role over real HTTP with real signed JWTs. Asserts no 500
from any (role, route) pair — a 500 on a seeded demo walk is a launch blocker regardless of
which agent's round introduced it."""

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

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")
os.environ.setdefault("MAISHA_SEED_ORG_ID", "org-7")

from fastapi.testclient import TestClient  # noqa: E402

from app.core import betterauth  # noqa: E402
from app.core.mahsa_client import MahsaClient  # noqa: E402
from app.core.rbac import Role  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_mahsa  # noqa: E402
from app.dev import seed as seed_mod  # noqa: E402
from app.main import app  # noqa: E402

pytestmark = pytest.mark.integration


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class _JWKSHandler(BaseHTTPRequestHandler):
    jwks_body: bytes = b'{"keys": []}'

    def do_GET(self) -> None:  # noqa: N802
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
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"walk-kid-{uuid.uuid4()}"
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
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    betterauth._jwks_client.cache_clear()
    monkeypatch.setenv("MAISHA_BETTER_AUTH_URL", base_url)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_AUDIENCE", raising=False)
    monkeypatch.delenv("MAISHA_BETTER_AUTH_MFA_CLAIM", raising=False)
    try:
        yield SimpleNamespace(base_url=base_url, kid=kid, priv_pem=priv_pem)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()


def _bearer(auth_server, role: Role) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": f"user-{role.value}",
            "email": f"{role.value}@example.com",
            "iss": auth_server.base_url,
            "aud": auth_server.base_url,
            "iat": now,
            "exp": now + 900,
            "activeOrganizationId": "org-7",
            "role": role.value,
            "plan": "growth",
        },
        auth_server.priv_pem,
        algorithm="EdDSA",
        headers={"kid": auth_server.kid},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(session, mahsa_server, auth_server, monkeypatch) -> TestClient:
    # Seed the demo tenant against org-7 (the org every minted JWT carries).
    monkeypatch.setattr(seed_mod, "DEMO_ORG", "org-7")
    monkeypatch.setattr(
        seed_mod,
        "_FOUNDER",
        seed_mod.Principal(
            user_id="founder", org_id="org-7", role=Role.OWNER, email="founder@acme-demo.in"
        ),
    )
    assert seed_mod.seed(session).get("skipped") is None
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_server)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_mahsa, None)


def _get_routes() -> list[str]:
    """Every GET path on the real app, parameterized ones filled from seeded facts."""
    from fastapi.routing import APIRoute

    def walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
                continue
            inner = getattr(r, "original_router", None)  # fastapi _IncludedRouter
            if inner is not None:
                yield from walk(inner.routes)
                continue
            sub = getattr(r, "routes", None)
            if sub:
                yield from walk(sub)

    paths: set[str] = set()
    for r in walk(app.routes):
        if "GET" not in (r.methods or set()):
            continue
        p = r.path
        if "{domain}" in p and "action" not in p:
            for d in (
                "treasury",
                "revenue",
                "payables",
                "payroll",
                "gst",
                "tax",
                "ledger",
                "forecast",
                "equity",
                "compliance",
                "expense",
                "vault",
            ):
                paths.add(p.replace("{domain}", d))
            continue
        if "{employee_id}" in p:
            paths.add(p.replace("{employee_id}", "1"))
            continue
        if "{" in p:
            continue  # remaining parameterized routes need bespoke ids; covered elsewhere
        paths.add(p)
    paths.discard("/login")  # redirects out
    return sorted(paths)


WEIRD_STATES = [
    "..",
    "%2e%2e%2fetc",
    "MANIFEST",
    "CHANGELOG",
    "mh'; DROP TABLE x;--",
    "ZZ",
    "mh ",
    " ",
    "TN%00",
    "\U0001f988",
]


def test_state_pack_adversarial(client, auth_server):
    h = _bearer(auth_server, Role.ACCOUNTANT)
    for s in WEIRD_STATES:
        r = client.get(f"/api/payroll/state-pack/{s}", headers=h)
        # Unknown states honestly answer 200/no_pack (statute data is not a secret);
        # anything else must be a clean 4xx — never a 500, never a computed figure.
        assert r.status_code in (200, 404, 409, 422), (s, r.status_code, r.text[:200])
        if r.status_code == 200:
            body = r.json()
            assert body["pt"].get("pt_status") == "no_pack", (s, body)
            assert "monthly" not in body and "half_yearly" not in body, (s, body)
    r = client.get("/api/payroll/state-pack/MH?gross_monthly_paise=-1&month=13", headers=h)
    assert r.status_code < 500, r.text[:300]
    r = client.get(
        "/api/payroll/state-pack/MH?gross_monthly_paise=99999999999999999999&month=1", headers=h
    )
    assert r.status_code < 500, r.text[:300]
    r = client.get(
        "/api/payroll/state-pack/TN?half_yearly_income_paise=100000&jurisdiction=../../x",
        headers=h,
    )
    assert r.status_code < 500, r.text[:300]


def test_legal_docs_adversarial(client, auth_server):
    h = _bearer(auth_server, Role.CA)
    # "dpdp_notice/.." is normalized to /api/legal/docs by the HTTP client itself (RFC 3986),
    # landing on the harmless status route — not server-side traversal.
    for d in ["../../../etc/passwd", "tos%2f..", "TOS"]:
        r = client.get(f"/api/legal/docs/{d}", headers=h)
        assert r.status_code in (404, 405, 307), (d, r.status_code)
    # Accepting an unpublished document must refuse (nothing to accept), never record.
    r = client.post("/api/legal/docs/tos/accept", headers=h, json={})
    assert r.status_code in (400, 403, 404, 409, 422), (r.status_code, r.text[:200])


def test_playbook_and_memory_adversarial(client, auth_server):
    h_owner = _bearer(auth_server, Role.OWNER)
    r = client.post("/api/playbook/NOPE/feedback", headers=h_owner, json={"verdict": "adopted"})
    assert r.status_code in (404, 422), r.text[:200]
    r = client.post(
        "/api/playbook/GST-LATEFEE/feedback", headers=h_owner, json={"verdict": "hacked"}
    )
    assert r.status_code in (400, 404, 422), r.text[:200]
    h_inv = _bearer(auth_server, Role.INVESTOR)
    r = client.get("/api/memory", headers=h_inv)
    assert r.status_code == 403, r.status_code
    h_ca = _bearer(auth_server, Role.CA)
    r = client.put("/api/memory", headers=h_ca, json={"content": "x"})
    assert r.status_code == 403, r.status_code
    r = client.put("/api/memory", headers=h_owner, json={"content": "A" * 5000})
    assert r.status_code == 422, (r.status_code, r.text[:200])


def test_rulepack_health_no_path_leak(client, auth_server):
    h = _bearer(auth_server, Role.INVESTOR)
    r = client.get("/api/health/rulepack", headers=h)
    assert r.status_code in (200, 403), r.status_code
    if r.status_code == 200:
        assert "/home/" not in r.text and "kiran" not in r.text.lower()


def test_seeded_walk_no_500_any_role(client: TestClient, auth_server) -> None:
    failures: list[str] = []
    routes = _get_routes()
    assert len(routes) > 40, routes  # the walk must actually cover the API surface
    for role in Role:
        headers = _bearer(auth_server, role)
        for path in routes:
            r = client.get(path, headers=headers)
            if r.status_code >= 500:
                failures.append(f"{role.value} GET {path} -> {r.status_code}: {r.text[:200]}")
    assert not failures, "\n".join(failures)
