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
from app.db.models.payroll import Employee  # noqa: E402
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
            # Top tier, so a WS6 entitlement 402 can never masquerade as (or mask) an RBAC
            # outcome anywhere in this matrix — this file isolates the capability layer.
            "plan": "growth",
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


# --------------------------------------------------------------------------------------------
# EVERY /api ROUTE x EVERY ROLE (fix:rbac-api)
#
# The four-route matrix above stays as-is (it proves the deep semantics — first-failing-gate,
# no-mutation-on-denial, attribution — over a live Mahsa). This section is the COVERAGE guard:
# every route under /api must declare its capability via app.core.rbac_deps, and every
# (role, route) pair is exercised over real HTTP with a real signed token.
# --------------------------------------------------------------------------------------------

_FILING_DETAIL = "statutory filing: requires Owner or Admin regardless of matrix_config"

#: gate name -> (roles allowed through it, the 403 detail a denied caller sees).
#: `filing` is the WS5.2 HARD gate (approval_matrix.decide_approval): Owner/Admin ONLY — note
#: it is STRICTER than the `approve_filing` capability (which Approver also holds).
GATES: dict[str, tuple[frozenset[Role], str]] = {
    "read": (
        frozenset({Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.APPROVER, Role.CA}),
        "missing capability: read",
    ),
    "write": (
        frozenset({Role.OWNER, Role.ADMIN, Role.ACCOUNTANT}),
        "missing capability: write",
    ),
    "approve_payment": (
        frozenset({Role.OWNER, Role.ADMIN, Role.APPROVER}),
        "missing capability: approve_payment",
    ),
    "view_audit": (
        frozenset({Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.APPROVER, Role.CA}),
        "missing capability: view_audit",
    ),
    "export": (
        frozenset({Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.CA}),
        "missing capability: export",
    ),
    "manage_users": (
        frozenset({Role.OWNER, Role.ADMIN}),
        "missing capability: manage_users",
    ),
    "filing": (frozenset({Role.OWNER, Role.ADMIN}), _FILING_DETAIL),
}

#: THE TABLE — every /api route, with its gates IN THE ORDER THE APP CHECKS THEM (router-level
#: baseline first, then route-level). Written out by hand, not derived from the app: a new /api
#: route fails the coverage test below until a human adds a row here and a gate on the route.
API_ROUTE_GATES: dict[str, tuple[str, ...]] = {
    # SPA surface (app/web/api_*.py)
    "GET /api/today": ("read",),
    "GET /api/inbox": ("read",),
    "POST /api/inbox/bulk": ("read",),  # + in-handler approve_payment on confirm=true (above)
    "GET /api/approvals": ("read",),
    "POST /api/approvals/{domain}/decide": ("approve_payment",),
    "GET /api/health/connections": ("read",),
    # WS1.E3 rule-pack version — read-only, behind the health router's READ gate.
    "GET /api/health/rulepack": ("read",),
    "GET /api/domains": ("read",),
    "GET /api/domains/{domain}": ("read",),
    # P2-3: trend series for the SPA sparklines — read-only, same query the HTMX page reads.
    "GET /api/domains/{domain}/history": ("read",),
    # P1-1 Ask Maisha SPA screen (app/web/api_domains.py): read-only, same pipeline as HTMX /ask.
    "POST /api/ask": ("read",),
    # P0-2 generic action preview/commit: preview is a dry-run (read, api_bulk precedent);
    # commit carries the capability the HTMX drawer flow already requires (write).
    "POST /api/domains/{domain}/actions/{key}/preview": ("read",),
    "POST /api/domains/{domain}/actions/{key}/commit": ("read", "write"),
    "GET /api/audit": ("read", "view_audit"),
    # WS8.1 audit pack (downloads additionally need export)
    "GET /api/audit/pack": ("read", "view_audit"),
    "GET /api/audit/pack.zip": ("read", "export"),
    "GET /api/audit/pack.pdf": ("read", "export"),
    # WS8.2 CA query threads: raise/read/resolve are Audit-Room actions (view_audit — CA holds
    # it); respond-with-doc is a books-side answer (write — CA is excluded by construction).
    "GET /api/audit/threads": ("read", "view_audit"),
    "POST /api/audit/threads": ("read", "view_audit"),
    "GET /api/audit/threads/{thread_id}": ("read", "view_audit"),
    "POST /api/audit/threads/{thread_id}/respond": ("read", "write"),
    "POST /api/audit/threads/{thread_id}/resolve": ("read", "view_audit"),
    "GET /api/audit/sample": ("read", "view_audit"),
    # WS8.3 CA seat onboarding: inviting is user management (Owner/Admin); accepting is done
    # by the invited CA's own token (no extra capability — identity IS the authorization).
    "POST /api/ca/invite": ("read", "manage_users"),
    # P1-3 settings surface: the pending-invites list carries the same gate as inviting.
    "GET /api/ca/pending": ("read", "manage_users"),
    "POST /api/ca/accept": ("read",),
    # P0-1 filing flow (app/web/api_filings.py): previews are readable (the queue is honest to
    # every role), confirms wear the WS5.2 statutory hard gate, evidence is an audit read.
    "GET /api/filings": ("read",),
    "POST /api/filings/gstr3b/preview": ("read",),
    "POST /api/filings/gstr3b/confirm": ("read", "filing"),
    "POST /api/filings/tds/preview": ("read",),
    "POST /api/filings/tds/confirm": ("read", "filing"),
    "POST /api/filings/deadline/{deadline_id}/preview": ("read",),
    "POST /api/filings/deadline/{deadline_id}/confirm": ("read", "filing"),
    "GET /api/filings/evidence": ("read", "view_audit"),
    # treasury
    "POST /api/treasury/accounts": ("read", "write"),
    # P0-5: the re-import account picker (Domain.tsx treasury) — read, same as every other list.
    "GET /api/treasury/accounts": ("read",),
    "POST /api/treasury/accounts/{account_id}/import": ("read", "write"),
    "GET /api/treasury/cash": ("read",),
    "GET /api/treasury/metrics": ("read",),
    "POST /api/treasury/fold": ("read",),
    # payroll
    "POST /api/payroll/employees": ("read", "write"),
    "POST /api/payroll/employees/{employee_id}/salary": ("read", "write"),
    "GET /api/payroll/preview": ("read",),
    "POST /api/payroll/runs": ("read", "write"),
    "POST /api/payroll/fold": ("read",),
    "GET /api/payroll/lwf": ("read",),
    # P0-4 payroll run flow (app/web/api_payroll.py): preview is a dry-run read (api_actions
    # precedent); confirm carries the same `write` the direct POST /runs already requires;
    # artifact downloads wear the same `export` gate as the audit-pack downloads.
    "GET /api/payroll/runs/overview": ("read",),
    "POST /api/payroll/runs/preview": ("read",),
    "POST /api/payroll/runs/confirm": ("read", "write"),
    "GET /api/payroll/employees/{employee_id}/payslip.pdf": ("read", "export"),
    "GET /api/payroll/employees/{employee_id}/form16.pdf": ("read", "export"),
    "GET /api/payroll/ecr.txt": ("read", "export"),
    # WS2.3 — state-pack PT provenance + pack-path computation (read-only, no export/write).
    "GET /api/payroll/state-pack/{state}": ("read",),
    # gst — filing a GSTR-3B is a statutory filing: WS5.2 hard gate, not a capability check
    "GET /api/gst/validate-gstin": ("read",),
    "POST /api/gst/gstr3b": ("read", "filing"),
    "POST /api/gst/gstr1": ("read",),  # builds the return payload; files nothing
    "GET /api/gst/itc/reconcile": ("read",),
    "POST /api/gst/fold": ("read",),
    # P2-2 GST detail SPA surface (app/web/api_gst.py): detail is a read; the IMS action route
    # is read at the router level with an in-handler `write` on confirm=true (api_bulk
    # precedent); artifact downloads wear the same `export` gate as every other /api download.
    "GET /api/gst/detail": ("read",),
    "POST /api/gst/ims/action": ("read",),
    "GET /api/gst/gstr1.json": ("read", "export"),
    "GET /api/gst/einvoice.json": ("read", "export"),
    # revenue
    "POST /api/revenue/customers": ("read", "write"),
    "POST /api/revenue/invoices": ("read", "write"),
    "GET /api/revenue/ar-aging": ("read",),
    "GET /api/revenue/dunning": ("read",),
    "POST /api/revenue/fold": ("read",),
    # payables
    "POST /api/payables/vendors": ("read", "write"),
    "POST /api/payables/bills": ("read", "write"),
    "GET /api/payables/ap-aging": ("read",),
    "GET /api/payables/itc": ("read",),
    "POST /api/payables/fold": ("read",),
    # tax — filing a TDS return is a statutory filing
    "POST /api/tax/tds-returns": ("read", "filing"),
    "GET /api/tax/tds-summary": ("read",),
    "POST /api/tax/advance-tax/234c": ("read",),
    "POST /api/tax/fold": ("read",),
    # ledger
    "POST /api/ledger/accounts": ("read", "write"),
    "POST /api/ledger/journal": ("read", "write"),
    "GET /api/ledger/trial-balance": ("read",),
    "GET /api/ledger/pnl": ("read",),
    "GET /api/ledger/balance-sheet": ("read",),
    "POST /api/ledger/fold": ("read",),
    # WS9.1 Tally import (app/web/api_tally.py): parse is the dry-run reconciliation report
    # (read, api_actions preview precedent); commit is the typed-confirm book write (write).
    "POST /api/ledger/tally/parse": ("read",),
    "POST /api/ledger/tally/commit": ("read", "write"),
    # P1-5 statements (app/web/api_statements.py) — read-only wrappers over LedgerService
    "GET /api/statements": ("read",),
    "GET /api/statements/gl/{account_id}": ("read",),
    # P1-4 investor-update preview (app/web/api_investor.py) — read-only wrapper over the
    # existing app.core.strategy.investor_update generator; sending stays on the HTMX surface.
    "POST /api/investor/preview": ("read",),
    # compliance — marking a deadline filed is a statutory filing
    "POST /api/compliance/deadlines": ("read", "write"),
    "POST /api/compliance/seed": ("read", "write"),
    "POST /api/compliance/deadlines/{deadline_id}/file": ("read", "filing"),
    "GET /api/compliance/alerts": ("read",),
    "POST /api/compliance/fold": ("read",),
    # WS1.B4 Labour-Code watch list — read-only, behind the compliance router's READ gate.
    "GET /api/compliance/watch": ("read",),
    # equity (entitlement 402s sit BEHIND the rbac gates and are tested elsewhere)
    "POST /api/equity/shareholders": ("read", "write"),
    "GET /api/equity/cap-table": ("read",),
    "POST /api/equity/safe/convert": ("read", "write"),
    "POST /api/equity/snapshot": ("read", "write"),
    "POST /api/equity/fold": ("read",),
    # forecast (project/scenario/unit-economics are pure compute — read)
    "POST /api/forecast/project": ("read",),
    "POST /api/forecast/scenario": ("read",),
    "POST /api/forecast/unit-economics": ("read",),
    "POST /api/forecast/forecasts": ("read", "write"),
    "POST /api/forecast/fold": ("read",),
    # expense
    "POST /api/expense/claims": ("read", "write"),
    "POST /api/expense/claims/{claim_id}/approve": ("read", "approve_payment"),
    "GET /api/expense/analytics": ("read",),
    "POST /api/expense/parse-receipt": ("read",),
    "POST /api/expense/ocr-receipt": ("read",),
    "POST /api/expense/fold": ("read",),
    # WS10.1 privacy surface (app/web/api_legal.py): the rights-request list and the notice
    # status are reads; accepting the notice is the verified caller binding THEMSELVES to a
    # published version (the /api/ca/accept precedent — identity IS the authorization), so it
    # carries the router's read baseline, not write: a read-only CA's acceptance is as real as
    # an Owner's. Raising a request goes through the generic action preview/commit rows above.
    "GET /api/legal/dpdp/requests": ("read",),
    "GET /api/legal/notice": ("read",),
    "POST /api/legal/notice/accept": ("read",),
    # WS10.4 — ToS/Privacy (and any DocType) served + versioned + acceptance-logged. POST
    # accept is deliberately read-gated: an acceptance is the verified caller binding
    # THEMSELVES to a published version — identity is the authorization (the /notice/accept
    # precedent above); it writes only the caller's own acceptance row.
    "GET /api/legal/docs": ("read",),
    "GET /api/legal/docs/{doc_type}": ("read",),
    "POST /api/legal/docs/{doc_type}/accept": ("read",),
    # SPEC-MEMCITE-1.0 MEM.P0-2 (§A9 OWNER-DECISION): memory steers the agent's narrative —
    # an admin surface. Owner/Admin write via the existing manage_users gate; every read role
    # (incl. CA, deliberately) may view the block and its history. Playbook feedback is a
    # books-side working decision: write (Owner/Admin/Accountant), the drawer-commit precedent.
    "GET /api/memory": ("read",),
    "PUT /api/memory": ("read", "manage_users"),
    "POST /api/memory/append": ("read", "manage_users"),
    "GET /api/memory/history": ("read",),
    "POST /api/playbook/{playbook_id}/feedback": ("read", "write"),
    # vault
    "POST /api/vault/documents": ("read", "write"),
    "GET /api/vault/search": ("read",),
    # P2-1: OCR-scan ingest, same gate as the text-content ingest above.
    "POST /api/vault/ocr-ingest": ("read", "write"),
    "POST /api/vault/fold": ("read",),
}

#: Marker a route's declared gates must carry, per gate name (the `filing` gate is declared by
#: require_filing, whose marker capability is approve_filing).
_GATE_MARKER = {
    "read": Capability.READ,
    "write": Capability.WRITE,
    "approve_payment": Capability.APPROVE_PAYMENT,
    "view_audit": Capability.VIEW_AUDIT,
    "export": Capability.EXPORT,
    "manage_users": Capability.MANAGE_USERS,
    "filing": Capability.APPROVE_FILING,
}


def _deployed_api_routes() -> dict[str, list[Capability]]:
    """Every (method, path) under /api on the REAL app, with the capability markers its
    dependencies declare (see app.core.rbac_deps.require / require_filing)."""
    from fastapi.routing import APIRoute

    from app.main import app as real_app

    def _walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r.methods, r.path, r.dependant
            elif type(r).__name__ == "_IncludedRouter":  # FastAPI's lazy include node
                for ctx in r.effective_route_contexts():
                    if ctx.dependant is not None:
                        yield ctx.methods, ctx.path, ctx.dependant

    deployed: dict[str, list[Capability]] = {}
    for methods, path, dependant in _walk(real_app.routes):
        if not path.startswith("/api"):
            continue
        for method in sorted(set(methods) - {"HEAD"}):
            caps = [
                cap
                for dep in dependant.dependencies
                if (cap := getattr(dep.call, "required_capability", None)) is not None
            ]
            deployed[f"{method} {path}"] = caps
    return deployed


def test_every_api_route_is_declared_and_gated() -> None:
    """The coverage guard. A new /api route fails here twice over: once for not being in
    API_ROUTE_GATES (a human must decide its capability), and once if it carries no
    rbac_deps marker (it was added to the table but never actually gated)."""
    deployed = _deployed_api_routes()

    assert set(deployed) == set(API_ROUTE_GATES), (
        f"routes only in app: {sorted(set(deployed) - set(API_ROUTE_GATES))}; "
        f"routes only in table: {sorted(set(API_ROUTE_GATES) - set(deployed))}"
    )
    for route_id, gate_names in API_ROUTE_GATES.items():
        expected_markers = [_GATE_MARKER[g] for g in gate_names]
        assert deployed[route_id] == expected_markers, (
            f"{route_id}: declares {deployed[route_id]}, table expects {expected_markers}"
        )


def _call(client: TestClient, route_id: str, headers: dict[str, str]) -> Response:
    method, _, path = route_id.partition(" ")
    for param, value in (
        ("{domain}", "treasury"),
        ("{account_id}", "1"),
        ("{employee_id}", "1"),
        ("{deadline_id}", "1"),
        ("{claim_id}", "1"),
        ("{thread_id}", "1"),
        ("{playbook_id}", "GST-LATEFEE"),
    ):
        path = path.replace(param, value)
    if method == "GET":
        return client.get(path, headers=headers)
    # An empty JSON body: enough to reach the dependency gates. For a PERMITTED caller the
    # route may then 422/400/404 on the body — that is fine; what it must never do is 401/403.
    if method == "PUT":
        return client.put(path, json={}, headers=headers)
    return client.post(path, json={}, headers=headers)


def test_full_api_matrix_every_route_x_every_role(client, auth_server) -> None:
    """Both directions for all of API_ROUTE_GATES x Role, real HTTP, real signed tokens.

    Denied: 403 naming the FIRST gate the role fails (router baseline before route gate).
    Permitted: anything but 401/402/403 — the caller got past authn + authz (a 422 for the
    garbage body is the route doing its job). One test, ~400 requests, one client."""
    failures: list[str] = []
    for role in Role:
        headers = _bearer(auth_server, role)
        for route_id, gate_names in API_ROUTE_GATES.items():
            denied_details = [
                GATES[g][1] for g in gate_names if role not in GATES[g][0]
            ]
            response = _call(client, route_id, headers)
            if denied_details:
                if response.status_code != 403:
                    failures.append(
                        f"{role.value} on {route_id}: expected 403, "
                        f"got {response.status_code}: {response.text[:120]}"
                    )
                elif response.json()["detail"] != denied_details[0]:
                    failures.append(
                        f"{role.value} on {route_id}: expected detail "
                        f"{denied_details[0]!r}, got {response.json()['detail']!r}"
                    )
            elif response.status_code in (401, 402, 403):
                failures.append(
                    f"{role.value} on {route_id}: must be PERMITTED past auth, "
                    f"got {response.status_code}: {response.text[:120]}"
                )
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------------------------------
# The HTMX surface carries the SAME decision (fix:rbac-api): approve/mutate routes are gated
# with the same deps, and a decision is attributed to the verified caller.
# --------------------------------------------------------------------------------------------


def test_htmx_decide_denies_accountant_and_attributes_to_the_verified_caller(
    client, auth_server, session
) -> None:
    """Spec negative: an Accountant must NOT be able to approve — on the HTMX form route too.
    And when an Approver does decide, the sealed Decision names the JWT's subject, not
    ``settings.default_user_id``."""
    denied = client.post(
        "/approvals/treasury/decide",
        data={"decision": "approved"},
        headers=_bearer(auth_server, Role.ACCOUNTANT),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: approve_payment"

    decided = client.post(
        "/approvals/treasury/decide",
        data={"decision": "approved"},
        headers=_bearer(auth_server, Role.APPROVER),
    )
    assert decided.status_code == 200

    from sqlalchemy import select

    from app.db.models.shared import Decision

    row = session.scalars(select(Decision).order_by(Decision.id.desc()).limit(1)).first()
    assert row is not None and row.user_id == "user-approver"


def test_htmx_bulk_preview_open_to_accountant_commit_is_not(client, auth_server) -> None:
    """The HTMX /inbox/bulk mirrors the JSON route's preview/commit split exactly."""
    headers = _bearer(auth_server, Role.ACCOUNTANT)
    preview = client.post(
        "/inbox/bulk",
        data={"action": "approve", "ids": ["approval:treasury"]},
        headers=headers,
    )
    assert preview.status_code == 200

    commit = client.post(
        "/inbox/bulk",
        data={"action": "approve", "ids": ["approval:treasury"], "confirm": "true"},
        headers=headers,
    )
    assert commit.status_code == 403
    assert "approve_payment" in commit.json()["detail"]


def test_htmx_action_submit_requires_write(client, auth_server) -> None:
    """CA (read-only) cannot mutate through the drawer form; Accountant (write) can."""
    denied = client.post(
        "/d/ledger/action/create-account",
        data={"code": "1000", "name": "Cash", "account_type": "asset"},
        headers=_bearer(auth_server, Role.CA),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: write"

    allowed = client.post(
        "/d/ledger/action/create-account",
        data={"code": "1000", "name": "Cash", "account_type": "asset"},
        headers=_bearer(auth_server, Role.ACCOUNTANT),
    )
    assert allowed.status_code == 200
    assert "created" in allowed.text


def test_statutory_filing_hard_gate_is_stricter_than_the_capability(
    client, auth_server
) -> None:
    """The Approver HOLDS approve_filing (rbac) and is still refused a statutory filing route:
    WS5.2's hard gate admits Owner/Admin only and cannot be configured away. Paired with the
    allow direction: Admin gets past the gate (422 on the empty body, never 403)."""
    denied = client.post(
        "/api/gst/gstr3b", json={}, headers=_bearer(auth_server, Role.APPROVER)
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == _FILING_DETAIL

    allowed = client.post("/api/gst/gstr3b", json={}, headers=_bearer(auth_server, Role.ADMIN))
    assert allowed.status_code == 422  # past both gates; the empty body is the only objection


# --------------------------------------------------------------------------------------------
# WS8.2 — CA query threads over real HTTP: full lifecycle chained into audit verify, role
# negatives on the respond gate, and sampling determinism through the org-bearing principal.
# --------------------------------------------------------------------------------------------


def _seed_vault_doc(session) -> str:
    from app.db.models.vault import Document

    doc_id = "e" * 64
    session.add(
        Document(
            id=doc_id, file_name="invoice.pdf", file_path="/vault/invoice.pdf",
            doc_type="invoice", upload_date="2026-07-01", sha256=doc_id,
        )
    )
    session.commit()
    return doc_id


def test_ca_thread_lifecycle_over_http_is_chained_and_role_gated(
    client, auth_server, session
) -> None:
    """CA raises -> CA is REFUSED respond (write) -> Accountant responds with a vault doc ->
    CA resolves -> the Audit Room reports the chain intact with all three sealed events,
    attributed to the verified JWT subjects."""
    doc_id = _seed_vault_doc(session)
    ca = _bearer(auth_server, Role.CA)

    raised = client.post(
        "/api/audit/threads",
        json={"domain": "ledger", "entry_ref": "journal:1", "question": "Support?"},
        headers=ca,
    )
    assert raised.status_code == 200, raised.text
    tid = raised.json()["id"]
    assert raised.json()["state"] == "open"
    assert raised.json()["raised_by"] == "user-ca"

    # Role negative on the REAL route: the CA cannot answer (or mutate) its own query.
    denied = client.post(
        f"/api/audit/threads/{tid}/respond",
        json={"doc_id": doc_id, "note": "self-answer"},
        headers=ca,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: write"

    # A respond pointing at a nonexistent vault doc is refused, not recorded.
    acct = _bearer(auth_server, Role.ACCOUNTANT)
    bad_doc = client.post(
        f"/api/audit/threads/{tid}/respond",
        json={"doc_id": "f" * 64, "note": "no such doc"},
        headers=acct,
    )
    assert bad_doc.status_code == 404

    responded = client.post(
        f"/api/audit/threads/{tid}/respond",
        json={"doc_id": doc_id, "note": "invoice attached"},
        headers=acct,
    )
    assert responded.status_code == 200, responded.text
    assert responded.json()["state"] == "responded"

    resolved = client.post(f"/api/audit/threads/{tid}/resolve", json={}, headers=ca)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "resolved"
    events = resolved.json()["events"]
    assert [e["event"] for e in events] == ["raise", "respond", "resolve"]
    assert [e["user_id"] for e in events] == ["user-ca", "user-accountant", "user-ca"]
    assert events[1]["doc_id"] == doc_id

    # The whole exchange is on the ONE hash chain and it still verifies.
    audit = client.get("/api/audit", headers=ca)
    assert audit.status_code == 200
    body = audit.json()
    assert body["chain_intact"] is True
    sealed_actions = [e["action"] for e in body["entries"]]
    for action in ("ca_thread.raise", "ca_thread.respond", "ca_thread.resolve"):
        assert action in sealed_actions
    sealed_hashes = {e["this_hash"] for e in body["entries"]}
    assert {e["audit_hash"] for e in events} <= sealed_hashes


def test_sampling_route_is_deterministic_for_the_principals_org(client, auth_server, session):
    from app.db.models.ledger import JournalEntry

    for i in range(6):
        session.add(
            JournalEntry(
                entry_date=f"2026-07-{i + 1:02d}", reference=f"V-{i + 1}",
                description=f"voucher {i + 1}", source="gst",
                total_debit=100_00, total_credit=100_00,
            )
        )
    session.commit()
    ca = _bearer(auth_server, Role.CA)
    params = {"domain": "gst", "date_from": "2026-07-01", "date_to": "2026-07-31", "n": 3}
    s1 = client.get("/api/audit/sample", params=params, headers=ca)
    s2 = client.get("/api/audit/sample", params=params, headers=ca)
    assert s1.status_code == 200, s1.text
    assert s1.json() == s2.json()
    assert len(s1.json()["sample"]) == 3
    assert s1.json()["population"] == 6


def test_threads_payload_carries_the_callers_own_capabilities(client, auth_server) -> None:
    """P1-2: the SPA renders respond/export controls from the payload's server-computed verdict,
    never a client-side role guess — so the payload must carry it, per role, truthfully."""
    ca = client.get("/api/audit/threads", headers=_bearer(auth_server, Role.CA)).json()
    assert ca["can_respond"] is False  # a CA can never answer its own query
    assert "missing capability: write" in ca["respond_denied_reason"]
    assert ca["can_export"] is True

    acct = client.get("/api/audit/threads", headers=_bearer(auth_server, Role.ACCOUNTANT)).json()
    assert acct["can_respond"] is True
    assert acct["respond_denied_reason"] is None
    assert acct["can_export"] is True

    approver = client.get("/api/audit/threads", headers=_bearer(auth_server, Role.APPROVER)).json()
    assert approver["can_export"] is False  # pack downloads must not render for an Approver


def test_htmx_thread_surface_carries_the_same_decision(client, auth_server, session) -> None:
    """The HTMX audit room mirrors the JSON gates: CA raises via the form (303 back to /audit),
    CA cannot respond there either, and the raised thread renders on the page."""
    doc_id = _seed_vault_doc(session)
    ca = _bearer(auth_server, Role.CA)

    raised = client.post(
        "/audit/threads",
        data={"domain": "ledger", "entry_ref": "journal:9", "question": "HTMX raise?"},
        headers=ca,
        follow_redirects=False,
    )
    assert raised.status_code == 303
    assert raised.headers["location"] == "/audit"

    denied = client.post(
        "/audit/threads/1/respond",
        data={"doc_id": doc_id, "note": "self"},
        headers=ca,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: write"

    page = client.get("/audit", headers=ca)
    assert page.status_code == 200
    assert "HTMX raise?" in page.text
    assert "journal:9" in page.text


# --------------------------------------------------------------------------------------------
# WS8.3 — CA seat onboarding over real HTTP: invite (Owner) -> accept (the CA's own token),
# free seat, referral events sealed append-only and PII-minimal.
# --------------------------------------------------------------------------------------------


def test_ca_invite_accept_lifecycle_and_referral_events(client, auth_server, session) -> None:
    from app.core import ca_seat
    from app.core.audit_store import load_chain_for, verify_chain_for

    owner = _bearer(auth_server, Role.OWNER)
    ca = _bearer(auth_server, Role.CA)  # token email is ca@example.com, org org-7

    # accepting before any invite exists is a 404, never a fabricated membership
    premature = client.post("/api/ca/accept", json={}, headers=ca)
    assert premature.status_code == 404

    invited = client.post("/api/ca/invite", json={"email": "ca@example.com"}, headers=owner)
    assert invited.status_code == 200, invited.text
    assert invited.json()["status"] == "pending"
    assert invited.json()["seat"] == "free_unlimited"

    # an Accountant cannot invite (spec negative), and the refusal names the gate
    denied = client.post(
        "/api/ca/invite", json={"email": "x@y.in"}, headers=_bearer(auth_server, Role.ACCOUNTANT)
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: manage_users"

    # P1-3 settings surface: the pending list carries the invite, same gate as inviting itself
    pending = client.get("/api/ca/pending", headers=owner)
    assert pending.status_code == 200, pending.text
    assert [i["email"] for i in pending.json()["invites"]] == ["ca@example.com"]
    pending_denied = client.get("/api/ca/pending", headers=_bearer(auth_server, Role.ACCOUNTANT))
    assert pending_denied.status_code == 403
    assert pending_denied.json()["detail"] == "missing capability: manage_users"

    # the CA accepts with their OWN verified token — matched on the token's email
    accepted = client.post("/api/ca/accept", json={}, headers=ca)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"
    assert accepted.json()["referred_org"] is False  # first org for this CA

    # accepted -> no longer "pending" (kills a filter that forgets the status column)
    after_accept = client.get("/api/ca/pending", headers=owner)
    assert after_accept.json()["invites"] == []

    # referral events sealed append-only on the org's chain, PII-minimal (hash, not address)
    chain = load_chain_for(session, "org-7")
    ca_events = [e for e in chain if e.action.startswith("ca_") and "." not in e.action]
    assert [e.action for e in ca_events] == [ca_seat.EVENT_INVITED, ca_seat.EVENT_JOINED]
    assert verify_chain_for(session, "org-7")
    assert all("ca@example.com" not in (e.query or "") for e in chain)
    assert ca_seat.email_sha256("ca@example.com") in (ca_events[0].query or "")

    # inviting the same CA again (any case) is refused and seals nothing further
    dup = client.post("/api/ca/invite", json={"email": "CA@example.com"}, headers=owner)
    assert dup.status_code == 409
    assert len(load_chain_for(session, "org-7")) == len(chain)


# --------------------------------------------------------------------------------------------
# P1-7 (contract T11) — FIELD-level RBAC masking, byte-level. Screen gates above prove who may
# open a route; these prove that a role allowed IN still cannot receive a sensitive ₹: the
# per-employee salary figure is absent from the RESPONSE BYTES for CA/Approver, replaced by
# {"restricted": true, "reason": ...}, and present for Owner/Admin/Accountant. Dropping the
# app.core.landing.mask_field call reintroduces the bytes and fails these directly.
# --------------------------------------------------------------------------------------------

_RESTRICTED_SALARY = {"restricted": True, "reason": "requires salary_detail clearance"}


def _seed_two_salaried_employees(session) -> None:
    """Two employees with DISTINCT odd salaries, so every aggregate total (which stays visible)
    differs from every per-employee figure (which must not appear) — the byte-level asserts
    below would be vacuous if a total could coincide with a part."""
    from app.domains.payroll.service import PayrollService

    svc = PayrollService()
    for code, name, basic, hra in (
        ("E1", "Asha", 9_876_543, 1_234_567),
        ("E2", "Vikram", 7_654_321, 2_345_671),
    ):
        emp = Employee(
            employee_code=code, name=name, date_of_joining="2026-01-05", state="KA"
        )
        session.add(emp)
        session.flush()
        svc.set_salary_structure(
            session, emp.id, effective_from="2026-06-01", basic=basic, hra=hra
        )
    session.commit()


def test_t11_overview_masks_per_employee_net_for_ca_and_approver(
    client, auth_server, session
) -> None:
    _seed_two_salaried_employees(session)

    # The unmasked truth first (Owner), so the byte-level assert checks REAL values.
    owner = client.get(
        "/api/payroll/runs/overview", headers=_bearer(auth_server, Role.OWNER)
    )
    assert owner.status_code == 200, owner.text
    nets = [e["monthly_net_paise"] for e in owner.json()["employees"]]
    assert len(nets) == 2 and all(isinstance(n, int) and n > 0 for n in nets)

    for role in (Role.CA, Role.APPROVER):
        resp = client.get(
            "/api/payroll/runs/overview", headers=_bearer(auth_server, role)
        )
        assert resp.status_code == 200, f"{role.value} holds read and must see the screen"
        body = resp.json()
        for emp in body["employees"]:
            # masked -> the exact restricted shape, with the reason (never blank/absent)
            assert emp["monthly_net_paise"] == _RESTRICTED_SALARY
        # BYTE-LEVEL: the salary value appears NOWHERE in the response body.
        for net in nets:
            assert str(net) not in resp.text, f"{role.value} received salary bytes"

    # the other cleared role: Accountant sees the values (non-Owner/Admin/Accountant rule)
    acct = client.get(
        "/api/payroll/runs/overview", headers=_bearer(auth_server, Role.ACCOUNTANT)
    )
    assert [e["monthly_net_paise"] for e in acct.json()["employees"]] == nets


def test_t11_run_preview_masks_per_employee_figures_but_keeps_totals(
    client, auth_server, session
) -> None:
    _seed_two_salaried_employees(session)
    body = {"month_year": "2026-07"}

    owner = client.post(
        "/api/payroll/runs/preview", json=body, headers=_bearer(auth_server, Role.OWNER)
    )
    assert owner.status_code == 200, owner.text
    per_emp_values = {
        str(f["value_paise"])
        for e in owner.json()["employees"]
        for f in e["figures"]
        if f["value_paise"]
    }
    total_values = {str(f["value_paise"]) for f in owner.json()["totals"] if f["value_paise"]}
    secret = per_emp_values - total_values  # values that exist ONLY per-employee
    assert secret, "seed must produce per-employee values distinct from every total"

    ca = client.post(
        "/api/payroll/runs/preview", json=body, headers=_bearer(auth_server, Role.CA)
    )
    assert ca.status_code == 200, ca.text
    preview = ca.json()
    for emp in preview["employees"]:
        for f in emp["figures"]:
            assert f["restricted"] is True
            assert f["reason"] == "requires salary_detail clearance"
            assert "value_paise" not in f and "working" not in f
            assert set(f) <= {"restricted", "reason", "target", "label"}
    # BYTE-LEVEL: no per-employee-only value appears anywhere in the CA's response.
    for v in secret:
        assert v not in ca.text, "CA received per-employee salary bytes"
    # aggregates stay honest and visible (the run's size is not a secret from the CA)
    assert [f["value_paise"] for f in preview["totals"]] == [
        f["value_paise"] for f in owner.json()["totals"]
    ]

    # Accountant (cleared, holds write): full figures — the flow is usable end-to-end.
    acct = client.post(
        "/api/payroll/runs/preview", json=body, headers=_bearer(auth_server, Role.ACCOUNTANT)
    )
    assert {
        str(f["value_paise"])
        for e in acct.json()["employees"]
        for f in e["figures"]
        if f["value_paise"]
    } == per_emp_values


def test_t11_domain_figures_and_after_figures_share_the_one_masking_boundary(
    client, auth_server, monkeypatch
) -> None:
    """The crash-era regression: api_domains._figures_for lost its role param while the
    api_actions after_figures call site kept it (the ORCH HOTFIX then dropped BOTH to unmasked
    2-arg). Rebuilt atomically: role is a required positional, and every figure list leaves
    through app.core.landing.mask_figures. No domain snapshot fact is in T11's sensitive set
    yet, so this drives one through the boundary and proves it byte-level; dropping the
    mask_figures call in _figures_for fails this directly, and reverting api_actions to a 2-arg
    call is a TypeError caught by test_preview_then_commit_creates_with_badged_after_figures."""
    from app.web import api_domains

    real_enrich = api_domains.enrich
    monkeypatch.setattr(
        api_domains,
        "enrich",
        lambda snapshot: {**real_enrich(snapshot), "monthly_net_paise": 4_242_424},
    )

    # presence for a cleared role — the value really flows when clearance holds
    owner = client.get("/api/domains/payroll", headers=_bearer(auth_server, Role.OWNER))
    assert owner.status_code == 200, owner.text
    unmasked = [f for f in owner.json()["figures"] if f.get("key") == "monthly_net_paise"]
    assert unmasked and unmasked[0]["raw"] == 4_242_424

    for role in (Role.CA, Role.APPROVER):
        resp = client.get("/api/domains/payroll", headers=_bearer(auth_server, role))
        assert resp.status_code == 200, f"{role.value} holds read and must see the screen"
        masked = [f for f in resp.json()["figures"] if f.get("key") == "monthly_net_paise"]
        assert len(masked) == 1
        assert masked[0]["restricted"] is True
        assert masked[0]["reason"] == "requires salary_detail clearance"
        # only identifying keys survive — never value-bearing ones (value/raw/state)
        assert set(masked[0]) <= {"restricted", "reason", "target", "key", "label"}
        # BYTE-LEVEL: the value appears nowhere in the body, raw or ₹-formatted
        assert "4242424" not in resp.text and "42,424" not in resp.text

    # the five-hub overview shares the helper — its coverage loop must not 500 either
    overview = client.get("/api/domains", headers=_bearer(auth_server, Role.CA))
    assert overview.status_code == 200, overview.text
