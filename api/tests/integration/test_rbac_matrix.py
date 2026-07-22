"""WS5.1 acceptance — "permission matrix test (every role x every route)", over REAL HTTP.

MASTER_PLAN §WS5.1's acceptance criterion is verbatim a permission matrix. This is it, and it is
deliberately built the expensive way:

  · The app under test is ``app.main.app`` — the object uvicorn serves, with the real
    ``_authenticate`` middleware and the real router set. No bare ``FastAPI()`` shell.
  · Identity is a REAL Ed25519-signed Better Auth JWT verified against a REAL localhost JWKS
    endpoint. Nothing overrides ``get_principal``; nothing sets ``request.state`` by hand. The
    only way a role reaches ``can()`` in these tests is through a signature check.
  · The matrix asserts BOTH directions. A matrix that only tests denials is half a test: it
    passes just as happily against a route that denies everyone, which is the failure mode that
    would take the Owner down with the attacker.

The expected column is not copied from the implementation — it is written out per (role, route)
from ``rbac.ROLE_CAPABILITIES``, so changing the policy data fails this test until the table here
is updated to match. That is the point.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Must be set before importing app.main (the module builds the app at import time).
os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from httpx import Response  # noqa: E402

from app.core import betterauth  # noqa: E402
from app.core.mahsa_client import MahsaClient  # noqa: E402
from app.core.money import Paise  # noqa: E402
from app.core.rbac import Capability, Role  # noqa: E402
from app.db.models.treasury import BankAccount, BankTransaction  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_mahsa  # noqa: E402
from app.main import app  # noqa: E402

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------------------------
# A real JWKS endpoint + real signed tokens (same construction as tests/integration/
# test_auth_e2e.py — unique kid per fixture instance, socket closed properly).
# --------------------------------------------------------------------------------------------


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
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"rbac-kid-{uuid.uuid4()}"
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
    # The legacy shared-password cookie must not be able to answer for any of these requests.
    monkeypatch.setenv("MAISHA_LEGACY_PASSWORD_AUTH", "0")
    try:
        yield SimpleNamespace(base_url=base_url, kid=kid, priv_pem=priv_pem)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()


def _bearer(auth_server, role: Role) -> dict[str, str]:
    """A real, signed, in-date token whose Better Auth ``role`` claim is ``role``."""
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
            "role": role.value,  # maps 1:1 via principal.BETTER_AUTH_ROLE_MAP
        },
        auth_server.priv_pem,
        algorithm="EdDSA",
        headers={"kid": auth_server.kid},
    )
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------------------------
# A live app: real Mahsa, an isolated DB seeded so the gated routes have real work to do.
# --------------------------------------------------------------------------------------------


def _seed_distressed_treasury(session) -> None:
    """₹3,00,000 cash against ₹9,00,000 burned -> ~1 month runway -> Mahsa returns a RED verdict
    with requires_approval, which is what puts a real, decidable treasury item in the queue.
    Without it a permitted caller would get 404 and the allow-direction would prove nothing."""
    acct = BankAccount(
        bank_name="HDFC",
        account_number="1",
        ifsc="HDFC0000001",
        current_balance=Paise.from_rupees(300000),
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id, txn_date="2026-05-10", debit=Paise.from_rupees(900000), credit=0
        )
    )
    session.commit()


@pytest.fixture
def client(session, mahsa_server, auth_server) -> TestClient:
    _seed_distressed_treasury(session)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_server)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_mahsa, None)


# --------------------------------------------------------------------------------------------
# THE MATRIX
# --------------------------------------------------------------------------------------------

#: (id, path-for-assertion, caller) for every route gated in this ticket.
#: Each route lists its gates IN THE ORDER THE APP CHECKS THEM. ``/api/inbox/bulk`` with
#: ``confirm=true`` has two: the route-level ``read`` dependency, then the in-handler
#: ``approve_payment`` check before anything is sealed. A caller is permitted only if it holds
#: every gate, and a denial must name the FIRST gate it fails — which is exactly what
#: distinguishes "Investor cannot even look" from "Accountant may look but not commit".
ROUTES: dict[
    str, tuple[str, tuple[Capability, ...], Callable[[TestClient, dict[str, str]], Response]]
] = {
    "GET /api/approvals": (
        "/api/approvals",
        (Capability.READ,),
        lambda c, h: c.get("/api/approvals", headers=h),
    ),
    "POST /api/approvals/{domain}/decide": (
        "/api/approvals/treasury/decide",
        (Capability.APPROVE_PAYMENT,),
        lambda c, h: c.post(
            "/api/approvals/treasury/decide",
            json={"decision": "approved", "confirm_text": "treasury"},
            headers=h,
        ),
    ),
    "POST /api/inbox/bulk (preview)": (
        "/api/inbox/bulk",
        (Capability.READ,),
        lambda c, h: c.post(
            "/api/inbox/bulk", json={"action": "approve", "ids": [], "confirm": False}, headers=h
        ),
    ),
    "POST /api/inbox/bulk (confirm)": (
        "/api/inbox/bulk",
        (Capability.READ, Capability.APPROVE_PAYMENT),
        lambda c, h: c.post(
            "/api/inbox/bulk", json={"action": "approve", "ids": [], "confirm": True}, headers=h
        ),
    ),
}

#: The EXPECTED column, written out from rbac.ROLE_CAPABILITIES rather than computed from it, so
#: a policy change fails here until someone re-reads this table.
#:   read            -> owner, admin, accountant, approver, ca   (not investor)
#:   approve_payment -> owner, admin, approver                   (not accountant, ca, investor)
ALLOWED: dict[Capability, frozenset[Role]] = {
    Capability.READ: frozenset({Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.APPROVER, Role.CA}),
    Capability.APPROVE_PAYMENT: frozenset({Role.OWNER, Role.ADMIN, Role.APPROVER}),
}

MATRIX = [
    pytest.param(role, route_id, id=f"{role.value}::{route_id}")
    for role in Role
    for route_id in ROUTES
]


@pytest.mark.parametrize(("role", "route_id"), MATRIX)
def test_permission_matrix(client, auth_server, role: Role, route_id: str) -> None:
    """Every role x every gated route, both directions, real HTTP, real signed token."""
    path, gates, call = ROUTES[route_id]
    missing = [c for c in gates if role not in ALLOWED[c]]
    response = call(client, _bearer(auth_server, role))

    if not missing:
        assert response.status_code == 200, (
            f"{role.value} holds {[c.value for c in gates]} and must be PERMITTED on "
            f"{route_id}; got {response.status_code}: {response.text[:300]}"
        )
        # A permitted call is not merely non-403: it did the work.
        assert response.json().get("mahsa_up") is True
    else:
        assert response.status_code == 403, (
            f"{role.value} lacks {missing[0].value} and must be DENIED on {route_id}; "
            f"got {response.status_code}: {response.text[:300]}"
        )
        detail = response.json()["detail"]
        # The FIRST gate it fails, not just "some 403" — this is what proves the two gates on
        # /api/inbox/bulk are really two different checks and not one relabelled.
        assert detail == f"missing capability: {missing[0].value}"
        # The ticket's rule 4: a reviewer injected request.url.path into the 403 detail and the
        # old test survived. Assert the resource is absent from the RESPONSE BODY, not just the
        # detail string, and assert it in a way that a path substring cannot slip past.
        assert path not in response.text
        assert "treasury" not in response.text.lower()


def test_denied_role_leaves_the_queue_untouched(client, auth_server) -> None:
    """A denial must not be a mutation. The Accountant is refused the decide route; the treasury
    approval is still pending afterwards, proving the 403 fired BEFORE record_decision ran."""
    denied = client.post(
        "/api/approvals/treasury/decide",
        json={"decision": "approved", "confirm_text": "treasury"},
        headers=_bearer(auth_server, Role.ACCOUNTANT),
    )
    assert denied.status_code == 403

    listing = client.get("/api/approvals", headers=_bearer(auth_server, Role.OWNER)).json()
    assert any(item["domain"] == "treasury" for item in listing["items"]), (
        "the denied decide must not have consumed the approval"
    )


def test_bulk_preview_is_open_to_accountant_but_commit_is_not(client, auth_server) -> None:
    """The preview/commit split on ONE route: the Accountant may size up a bulk accept and may
    not perform one. If both used the same capability this test would fail in one direction."""
    headers = _bearer(auth_server, Role.ACCOUNTANT)
    preview = client.post(
        "/api/inbox/bulk", json={"action": "approve", "ids": [], "confirm": False}, headers=headers
    )
    assert preview.status_code == 200

    commit = client.post(
        "/api/inbox/bulk", json={"action": "approve", "ids": [], "confirm": True}, headers=headers
    )
    assert commit.status_code == 403
    assert "approve_payment" in commit.json()["detail"]


def test_decision_is_attributed_to_the_verified_caller_not_a_settings_default(
    client, auth_server
) -> None:
    """The receipt names the JWT's subject. This is what stops the audit trail recording every
    approval as one shared default user — and it fails if the route reverts to
    ``settings.default_user_id``."""
    receipt = client.post(
        "/api/approvals/treasury/decide",
        json={"decision": "approved", "confirm_text": "treasury"},
        headers=_bearer(auth_server, Role.APPROVER),
    )
    assert receipt.status_code == 200
    assert receipt.json()["receipt"]["user_id"] == "user-approver"


def test_unauthenticated_request_to_a_gated_route_is_401_not_403(client) -> None:
    """No token at all, with legacy password auth off: the request never reaches the capability
    check. 401 (who are you) is the correct answer, not 403 (you may not)."""
    response = client.get("/api/approvals")
    assert response.status_code == 401
