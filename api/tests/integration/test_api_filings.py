"""P0-1 filing flow over real HTTP: preview → typed confirm → receipt → attempt evidence.

What each test is built to kill (mutation-proofing, per the ticket):
  · round trip        — kills a confirm that stops writing the filing row or the audit seal,
                        and a preview whose badge states are hardcoded rather than produced by
                        Mahsa's live recompute (the late-fee figure must be ``verified`` because
                        the REAL engine recomputed it, and ``total_payable`` must stay ◐).
  · Accountant 403    — kills removal of ``require_filing`` from the confirm route (the WS5.2
                        hard gate), and asserts the DENIAL wrote nothing.
  · tamper            — kills skipping the confirm-token recomputation: a token minted over a
                        different preview's inputs/figures must be refused with 409 and must
                        write nothing.
  · typed confirm     — kills dropping the typed-phrase check (400, nothing written).
  · deadline flow     — kills an invented ₹ for an unported fee (value stays null / ◐) and the
                        wiring into the existing ``mark_filed`` write.
  · evidence          — kills the evidence bundle losing the sealed figures/trace ids, and the
                        recorded-vs-portal honesty labels (T5).

Identity is a REAL Ed25519-signed JWT against a real localhost JWKS endpoint (same
construction as test_rbac_matrix.py / test_auth_e2e.py) — the hard gate is exercised through
the same middleware production uses, not a dependency override.
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

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import betterauth  # noqa: E402
from app.core.audit import verify_chain  # noqa: E402
from app.core.audit_store import load_chain  # noqa: E402
from app.core.mahsa_client import MahsaClient  # noqa: E402
from app.core.rbac import Role  # noqa: E402
from app.db.models.gst import GstReturn  # noqa: E402
from app.db.models.shared import ComplianceCalendar  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_mahsa  # noqa: E402
from app.domains.gst import gst_calc  # noqa: E402
from app.main import app  # noqa: E402

pytestmark = pytest.mark.integration

_FILING_DETAIL = "statutory filing: requires Owner or Admin regardless of matrix_config"


# ── real JWKS + signed tokens (same construction as test_rbac_matrix.py) ─────────────────


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
    kid = f"filing-kid-{uuid.uuid4()}"
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
def client(session, mahsa_server, auth_server) -> TestClient:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_server)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_mahsa, None)


# ── payloads ─────────────────────────────────────────────────────────────────────────────

#: A GSTR-3B filed 3 days late: ₹1,00,000 IGST output against ₹40,000 IGST credit ⇒ real cash,
#: real late fee, real interest — every ported figure has something non-zero to verify.
GSTR3B = {
    "filing_period": "2026-07",
    "due_date": "2026-08-20",
    "filed_date": "2026-08-23",
    "is_nil": False,
    "output": {"igst": 100_000_00, "cgst": 0, "sgst": 0},
    "itc_available": {"igst": 40_000_00, "cgst": 0, "sgst": 0},
}


def _fig(preview: dict, target: str) -> dict:
    return next(f for f in preview["figures"] if f["target"] == target)


# ── the round trip ───────────────────────────────────────────────────────────────────────


def test_gstr3b_preview_confirm_roundtrip(client, auth_server, session) -> None:
    owner = _bearer(auth_server, Role.OWNER)

    preview = client.post("/api/filings/gstr3b/preview", json=GSTR3B, headers=owner)
    assert preview.status_code == 200, preview.text
    p = preview.json()

    # §0.4: the badge states come from Mahsa's LIVE recompute, not optimism. The late fee and
    # interest are ported targets, so with the real engine up they verify to the paisa; the
    # total is a sum with no recompute target and must stay honest_pending forever.
    assert p["mahsa_up"] is True
    days_late = 3
    expected_fee = gst_calc.late_fee_3b(days_late)
    assert _fig(p, "late_fee_3b")["value_paise"] == expected_fee
    assert _fig(p, "late_fee_3b")["state"] == "verified"
    assert _fig(p, "interest_3b")["state"] == "verified"
    assert _fig(p, "itc_setoff")["state"] == "verified"
    assert _fig(p, "itc_setoff")["value_paise"] == 60_000_00  # 1,00,000 − 40,000 ITC, in paise
    assert _fig(p, "total_payable")["state"] == "honest_pending"
    assert p["verdict_hash"], "verified figures must be sealed into a verdict"
    # The working panel is a real panel (T7), with statute citations, not a tooltip.
    assert _fig(p, "late_fee_3b")["working"]["citations"] == [
        {"text": "CGST Act s.47; Notf 19/2021-Central Tax"}
    ]

    # Preview wrote NO filing row (INVARIANT 9: preview is not a mutation of the books)…
    assert session.scalars(select(GstReturn)).all() == []
    # …but it DID seal attempt evidence.
    assert any(e.action == "filing.preview" for e in load_chain(session))

    # Confirm with the preview's own token + the typed phrase.
    confirm = client.post(
        "/api/filings/gstr3b/confirm",
        json={
            "inputs": GSTR3B,
            "confirm_token": p["confirm_token"],
            "confirm_text": "gstr-3b",  # case/space-insensitive, same rule as approvals
            "trace_id": p["trace_id"],
        },
        headers=owner,
    )
    assert confirm.status_code == 200, confirm.text
    r = confirm.json()

    # T5: the receipt is honest about WHAT was recorded — in-app, never a portal submission.
    assert r["recorded_as"] == "recorded_in_app"
    assert r["portal_submission"] is False
    assert "portal acknowledgement" in r["label"]
    assert r["trace_id"] == p["trace_id"]
    assert r["user_id"] == "user-owner"

    # The filing row the EXISTING service write produces, with the exact previewed figures.
    row = session.scalars(select(GstReturn)).one()
    assert row.status == "filed"
    assert row.late_fee == expected_fee

    # The audit receipt is sealed and the chain still verifies.
    chain = load_chain(session)
    recorded = [e for e in chain if e.action == "filing.recorded"]
    assert len(recorded) == 1
    assert recorded[0].this_hash == r["audit_hash"]
    detail = json.loads(recorded[0].query)
    assert detail["trace_id"] == p["trace_id"]
    assert detail["verdict_hash"] == r["verdict_hash"]
    assert verify_chain(chain)


def test_accountant_sees_queue_and_preview_but_confirm_is_403(client, auth_server, session) -> None:
    acct = _bearer(auth_server, Role.ACCOUNTANT)

    # The queue is visible and says WHY the confirm is out of reach (capability-derived).
    queue = client.get("/api/filings", headers=acct)
    assert queue.status_code == 200
    assert queue.json()["can_confirm"] is False
    assert queue.json()["confirm_denied_reason"] == _FILING_DETAIL

    # Preview is open (review is a read) and repeats the same denial reason for the UI.
    preview = client.post("/api/filings/gstr3b/preview", json=GSTR3B, headers=acct)
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p["can_confirm"] is False
    assert p["confirm_denied_reason"] == _FILING_DETAIL

    # The confirm is the WS5.2 hard gate: 403 with the gate's own words, and NOTHING written.
    denied = client.post(
        "/api/filings/gstr3b/confirm",
        json={"inputs": GSTR3B, "confirm_token": p["confirm_token"], "confirm_text": "GSTR-3B"},
        headers=acct,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == _FILING_DETAIL
    assert session.scalars(select(GstReturn)).all() == []
    assert not any(e.action == "filing.recorded" for e in load_chain(session))


def test_confirm_token_from_a_different_preview_is_rejected(client, auth_server, session) -> None:
    owner = _bearer(auth_server, Role.OWNER)
    p = client.post("/api/filings/gstr3b/preview", json=GSTR3B, headers=owner).json()

    # Same token, DIFFERENT inputs (output tax bumped ₹1): the server recomputes the token from
    # what was actually submitted, so the stale token cannot authorize the changed figures.
    tampered = {**GSTR3B, "output": {"igst": 100_001_00, "cgst": 0, "sgst": 0}}
    refused = client.post(
        "/api/filings/gstr3b/confirm",
        json={"inputs": tampered, "confirm_token": p["confirm_token"], "confirm_text": "GSTR-3B"},
        headers=owner,
    )
    assert refused.status_code == 409
    assert "different preview" in refused.json()["detail"]
    assert "Nothing was written" in refused.json()["detail"]
    assert session.scalars(select(GstReturn)).all() == []
    assert not any(e.action == "filing.recorded" for e in load_chain(session))


def test_typed_confirmation_must_match(client, auth_server, session) -> None:
    owner = _bearer(auth_server, Role.OWNER)
    p = client.post("/api/filings/gstr3b/preview", json=GSTR3B, headers=owner).json()
    refused = client.post(
        "/api/filings/gstr3b/confirm",
        json={"inputs": GSTR3B, "confirm_token": p["confirm_token"], "confirm_text": "gstr3b"},
        headers=owner,
    )
    assert refused.status_code == 400
    assert "Nothing was written" in refused.json()["detail"]
    assert session.scalars(select(GstReturn)).all() == []


def test_deadline_flow_never_invents_a_fee_and_marks_filed(client, auth_server, session) -> None:
    session.add(
        ComplianceCalendar(
            domain="roc", form_name="AOC-4", due_date="2026-06-30", filing_period="FY25-26"
        )
    )
    session.commit()
    row_id = session.scalars(select(ComplianceCalendar)).one().id
    admin = _bearer(auth_server, Role.ADMIN)

    # The queue lists it, overdue, routed to the generic flow.
    queue = client.get("/api/filings", headers=admin).json()
    item = next(i for i in queue["items"] if i["form_name"] == "AOC-4")
    assert item["kind"] == "deadline"
    assert item["days_overdue"] > 0

    body = {"filed_date": "2026-07-22", "acknowledgement": "ACK-123"}
    p = client.post(f"/api/filings/deadline/{row_id}/preview", json=body, headers=admin).json()
    # T12: no ported fee for AOC-4 ⇒ the amount is UNKNOWN (null) and ◐ — never an invented ₹.
    fee = _fig(p, "portal_fee")
    assert fee["value_paise"] is None
    assert fee["state"] == "honest_pending"
    assert "we don't guess" in fee["working"]["note"]

    confirm = client.post(
        f"/api/filings/deadline/{row_id}/confirm",
        json={"inputs": body, "confirm_token": p["confirm_token"], "confirm_text": "aoc-4"},
        headers=admin,
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["portal_submission"] is False
    row = session.get(ComplianceCalendar, row_id)
    assert row.status == "filed" and row.filed_date == "2026-07-22"
    assert row.acknowledgement == "ACK-123"


def test_attempt_evidence_bundle_carries_figures_verdicts_and_traces(
    client, auth_server, session
) -> None:
    owner = _bearer(auth_server, Role.OWNER)
    p = client.post("/api/filings/gstr3b/preview", json=GSTR3B, headers=owner).json()
    client.post(
        "/api/filings/gstr3b/confirm",
        json={
            "inputs": GSTR3B,
            "confirm_token": p["confirm_token"],
            "confirm_text": "GSTR-3B",
            "trace_id": p["trace_id"],
        },
        headers=owner,
    )

    evidence = client.get("/api/filings/evidence", headers=owner)
    assert evidence.status_code == 200
    b = evidence.json()
    # T5 honesty: what it proves and what it deliberately does not.
    assert "portal" in b["what_this_does_not_prove"].lower()
    assert b["event_count"] == 2
    actions = [e["action"] for e in b["events"]]
    assert actions == ["filing.preview", "filing.recorded"]
    for e in b["events"]:
        assert e["timestamp"] and e["audit_hash"]
        assert e["detail"]["trace_id"] == p["trace_id"]
        figs = {f["target"]: f for f in e["detail"]["figures"]}
        assert figs["late_fee_3b"]["state"] == "verified"
        assert e["detail"]["verdict_hash"] == p["verdict_hash"]
