"""WS7.6 — the approvals JSON API against the REAL Mahsa binary.

What is actually pinned here (not shape-checking):
  1. The listing RESTATES the figures being approved, and their verification state comes from a
     live Mahsa recompute — a matching figure verifies, a tampered book makes the same figure
     ``unbacked``. No verified state is ever fabricated.
  2. A decision returns an audit receipt whose hash is really present in the hash-chained log.
  3. Mahsa down cannot produce a verified-looking approval, and cannot record a decision at all.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.betterauth import get_principal
from app.core.mahsa_client import MahsaClient
from app.core.money import Paise
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.gst import GstReturn
from app.db.models.payables import Bill, Vendor
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.gst.service import GstService
from app.domains.payables.service import PayablesService
from app.web.api_approvals import router

pytestmark = pytest.mark.integration


def _client(session: Session, mahsa_url: str) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_url)
    # WS5.1: these routes are capability-gated. This file tests the RESTATEMENT logic, not RBAC,
    # so it overrides the one auth seam with an Owner. RBAC itself is proven over real HTTP with
    # real signed tokens in tests/integration/test_rbac_matrix.py.
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    return TestClient(app)


def _msme_bill_overdue(session: Session) -> Bill:
    """An MSME vendor unpaid well past 45 days (PAYABLES-001 -> yellow -> requires approval),
    on a TDS-bearing bill so payables also emits a real Prime-Directive recompute claim."""
    vendor = Vendor(
        name="Nano Tools",
        gstin="27AAAPA1234A1Z5",
        pan="AAAPA1234A",
        payee_type="company",
        tds_section="194J",
        msme_status=1,
        msme_type="micro",
        payment_terms=30,
    )
    session.add(vendor)
    session.flush()
    created = PayablesService().create_bill(
        session,
        vendor_id=vendor.id,
        bill_number="B-1",
        bill_date="2026-01-05",  # >45 days unpaid at any plausible run date
        subtotal=Paise.from_rupees(500000),
    )
    session.commit()
    bill = session.get(Bill, created["bill_id"])
    assert bill is not None and int(bill.tds_amount) > 0  # the claim needs a real TDS figure
    return bill


def _payables(body: dict) -> dict:
    items = [i for i in body["items"] if i["domain"] == "payables"]
    assert items, f"payables should need approval; got {[i['domain'] for i in body['items']]}"
    return items[0]


async def test_listing_restates_figures_with_live_verification(session, mahsa_server):
    _msme_bill_overdue(session)
    client = _client(session, mahsa_server)

    body = client.get("/api/approvals").json()
    assert body["mahsa_up"] is True
    item = _payables(body)

    # The figures behind the approval are restated, and at least one really verified.
    verified = [f for f in item["figures"] if f["state"] == "verified"]
    assert verified, item["figures"]
    assert all(f["state"] in ("verified", "honest_pending", "unbacked") for f in item["figures"])
    # Verified => Mahsa produced a recomputation; the total is real paise, not invented.
    assert item["verified_total_paise"] == sum(
        f["recomputed_paise"] for f in verified if f["recomputed_paise"] is not None
    )
    assert item["verdict_hash"] and len(item["verdict_hash"]) == 64
    assert item["rule_pack_version"]
    # The verdict Mahsa reached is carried, with its statutory citation.
    assert item["status"] in ("yellow", "red")
    assert any("MSMED" in c["citation"] for c in item["citations"])


async def test_tampered_book_makes_the_same_figure_unbacked(session, mahsa_server):
    """The verification state is not decorative: corrupt the stored TDS and the restated figure
    stops verifying rather than sailing through as ✓."""
    bill = _msme_bill_overdue(session)
    client = _client(session, mahsa_server)
    before = _payables(client.get("/api/approvals").json())
    assert any(f["state"] == "verified" for f in before["figures"])

    bill.tds_amount = int(bill.tds_amount) + 100  # ₹1 of drift
    session.commit()

    after = _payables(client.get("/api/approvals").json())
    # Payables can no longer stand behind that TDS figure at all, so the approval degrades to an
    # explicitly unverified one — it does not keep the ✓ and it does not go quiet.
    assert not any(f["state"] == "verified" for f in after["figures"])
    assert after["verdict_hash"] is None
    assert after["figures_note"]  # honest-empty says WHY
    assert after["verified_total_paise"] is None  # never ₹0 to stand in for "unknown"


async def test_mismatched_figure_is_unbacked_not_verified(session, mahsa_server):
    """A claim Mahsa CAN recompute but that does not match renders ``unbacked`` (✕) inside the
    approval — the human sees exactly which figure failed instead of an unqualified ✓."""
    svc = GstService()
    svc.file_gstr3b(
        session,
        filing_period="2026-04",
        due_date="2026-05-20",
        output={"igst": Paise.from_rupees(50000), "cgst": 0, "sgst": 0},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
        filed_date="2026-06-10",  # late -> GST-001 fires AND interest_3b is claimable
    )
    session.commit()
    client = _client(session, mahsa_server)

    def gst(body: dict) -> dict:
        items = [i for i in body["items"] if i["domain"] == "gst"]
        assert items, [i["domain"] for i in body["items"]]
        return items[0]

    item = gst(client.get("/api/approvals").json())
    interest = [f for f in item["figures"] if f["target"] == "interest_3b"]
    assert interest and interest[0]["state"] == "verified"

    ret = session.scalars(select(GstReturn)).first()
    assert ret is not None
    ret.interest = int(ret.interest) + 100  # ₹1 of drift on a recomputable figure
    session.commit()

    after = gst(client.get("/api/approvals").json())
    bad = [f for f in after["figures"] if f["target"] == "interest_3b"]
    assert bad and bad[0]["state"] == "unbacked"
    assert bad[0]["recomputed_paise"] != bad[0]["claimed_paise"]
    assert after["unverified_count"] >= 1 and after["all_verified"] is False


async def test_decision_returns_receipt_present_in_the_audit_chain(session, mahsa_server):
    _msme_bill_overdue(session)
    client = _client(session, mahsa_server)

    resp = client.post(
        "/api/approvals/payables/decide",
        json={"decision": "approved", "confirm_text": "payables"},
    )
    assert resp.status_code == 200
    receipt = resp.json()["receipt"]
    assert receipt["decision"] == "approved"
    assert receipt["timestamp"] and len(receipt["audit_hash"]) == 64

    chain = load_chain(session)
    assert verify_chain(chain) is True
    sealed = [e for e in chain if e.this_hash == receipt["audit_hash"]]
    assert sealed and sealed[0].action == "approval.approved"

    # ...and the item leaves the pending queue.
    body = client.get("/api/approvals").json()
    assert not [i for i in body["items"] if i["domain"] == "payables"]


async def test_confirm_text_gates_the_mutation(session, mahsa_server):
    _msme_bill_overdue(session)
    client = _client(session, mahsa_server)

    resp = client.post(
        "/api/approvals/payables/decide",
        json={"decision": "approved", "confirm_text": "yes"},
    )
    assert resp.status_code == 400
    assert "Nothing was written" in resp.json()["detail"]
    assert load_chain(session) == []  # nothing sealed


async def test_unknown_domain_is_404(session, mahsa_server):
    client = _client(session, mahsa_server)
    resp = client.post(
        "/api/approvals/not-a-domain/decide",
        json={"decision": "approved", "confirm_text": "not-a-domain"},
    )
    assert resp.status_code == 404


def test_mahsa_down_cannot_look_verified_and_cannot_decide(session):
    client = _client(session, "http://127.0.0.1:9")  # dead port

    body = client.get("/api/approvals").json()
    assert body["mahsa_up"] is False
    assert body["items"] == []  # honest-empty, never a figure that looks verified
    assert "unreachable" in body["message"]

    resp = client.post(
        "/api/approvals/payables/decide",
        json={"decision": "approved", "confirm_text": "payables"},
    )
    assert resp.status_code == 503
    assert load_chain(session) == []
