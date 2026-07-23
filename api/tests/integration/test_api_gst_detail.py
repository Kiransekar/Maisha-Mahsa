"""P2-2 — /api/gst detail flows: ITC recon honesty, IMS preview→confirm, artifact downloads.

Pinned here (not shape-checking):
  1. §0.4 fail-closed: no recon/IMS figure arrives ``verified`` — none of these aggregates is
     a ported Mahsa recompute target, so every badge must read ``honest_pending``. A fabricated
     ✓ on this surface is the exact defect the badge machinery exists to prevent.
  2. INVARIANT 9: the IMS preview mutates NOTHING (asserted against the DB), and a confirm
     without a matching preview token — or with a selection changed after the preview — is a
     409 that writes nothing.
  3. RBAC: downloads are read+export (Approver holds neither export nor write: 403); the IMS
     confirm needs ``write`` (CA can preview, cannot commit).
  4. WS9.3: the e-invoice artifact carries the draft-IRN honesty label verbatim, and /detail
     ships the same label for the SPA surface to render.
  5. §0.6: QRMP/CMP-08 obligations arrive ``pending_ca`` — no statutory due date is guessed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.gst import ItcRegister
from app.db.models.revenue import Customer
from app.db.session import get_session
from app.domains.gst.gst_calc import DRAFT_IRN_LABEL
from app.domains.revenue.service import RevenueService
from app.web.api_gst import router

pytestmark = pytest.mark.integration


def _client(session: Session, role: Role) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    return TestClient(app)


def _seed_itc(session: Session) -> dict[str, int]:
    """Three register rows: matched, claimed-but-not-in-2B, in-2B-but-not-claimed."""
    rows = {
        "matched": ItcRegister(
            gstin_supplier="29AAAAA0000A1Z5", invoice_number="M-1", invoice_date="2026-07-01",
            taxable_value=100_000_00, total_tax=18_000_00, eligible_itc=1, in_2b=1,
        ),
        "books_only": ItcRegister(
            gstin_supplier="29BBBBB0000B1Z5", invoice_number="B-2", invoice_date="2026-07-02",
            taxable_value=50_000_00, total_tax=9_000_00, eligible_itc=1, in_2b=0,
        ),
        "twob_only": ItcRegister(
            gstin_supplier="29CCCCC0000C1Z5", invoice_number="C-3", invoice_date="2026-07-03",
            taxable_value=20_000_00, total_tax=3_600_00, eligible_itc=0, in_2b=1,
        ),
    }
    session.add_all(rows.values())
    session.commit()
    return {k: r.id for k, r in rows.items()}


# ── (a) ITC reconciliation ────────────────────────────────────────────────────────


def test_detail_recon_badged_honest_and_mismatches_named(session):
    ids = _seed_itc(session)
    data = _client(session, Role.ACCOUNTANT).get("/api/gst/detail").json()

    figures = {f["key"]: f for f in data["recon"]["figures"]}
    # The exact reconcile_itc aggregates (available_2b counts rows that are BOTH in 2B and
    # eligible — the twob_only row is not eligible), ₹ rendered by the canonical renderer.
    assert figures["available_2b_paise"]["raw"] == 18_000_00
    assert figures["claimed_paise"]["raw"] == 18_000_00 + 9_000_00
    assert figures["available_2b_paise"]["value"].startswith("₹")
    # §0.4 fail-closed: none of these is a ported recompute target — a "verified" here is a lie.
    assert all(f["state"] == "honest_pending" for f in data["recon"]["figures"])

    mismatches = {m["id"]: m for m in data["recon"]["mismatches"]}
    assert set(mismatches) == {ids["books_only"], ids["twob_only"]}
    assert mismatches[ids["books_only"]]["kind"] == "books_not_in_2b"
    assert "Rule 36(4)" in mismatches[ids["books_only"]]["note"]
    assert mismatches[ids["twob_only"]]["kind"] == "in_2b_not_claimed"
    # every mismatch ₹ is badged, honestly ◐
    assert all(m["figure"]["state"] == "honest_pending" for m in mismatches.values())

    r364 = data["recon"]["rule_36_4"]
    assert (r364["statute"], r364["section"]) == ("CGST Rules 2017", "Rule 36(4)")

    # WS9.3 label ships to the SPA surface verbatim.
    assert data["draft_irn_label"] == DRAFT_IRN_LABEL


def test_detail_obligations_are_pending_ca_never_guessed(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "gst_filing_profile", "composition")
    data = _client(session, Role.OWNER).get("/api/gst/detail").json()
    obl = data["obligations"]
    assert obl["profile"] == "composition"
    assert [o["form"] for o in obl["obligations"]] == ["CMP-08"]
    # §0.6: no statutory due date exists in the spec — pending_ca, and no date invented.
    assert all(o["pending_ca"] and o["due_date"] is None for o in obl["obligations"])


def test_detail_qrmp_calendar_lists_pmt06_iff_and_quarterly_returns(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "gst_filing_profile", "qrmp")
    data = _client(session, Role.OWNER).get("/api/gst/detail").json()
    forms = [o["form"] for o in data["obligations"]["obligations"]]
    assert forms == ["PMT-06", "IFF", "PMT-06", "IFF", "GSTR-1", "GSTR-3B"]


# ── (c) IMS preview→confirm ───────────────────────────────────────────────────────


def test_ims_preview_states_the_change_and_mutates_nothing(session):
    ids = _seed_itc(session)
    client = _client(session, Role.ACCOUNTANT)
    res = client.post(
        "/api/gst/ims/action",
        json={"action": "accept", "ids": [ids["books_only"], 99999], "confirm": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["committed"] is False and body["preview_token"]
    (row,) = body["rows"]
    assert (row["current_state"], row["will_state"]) == ("pending", "accepted")
    # BLOCKED-CA honesty: deemed-accept was not evaluated, and the payload says so.
    assert body["deadline_pending_ca"] is True
    # the unknown id is accounted for, never silently dropped
    assert body["skipped"][0]["id"] == 99999
    # INVARIANT 9: the preview wrote nothing.
    actions = session.scalars(select(ItcRegister.ims_action)).all()
    assert set(actions) == {None}


def test_ims_confirm_without_preview_is_409_and_writes_nothing(session):
    ids = _seed_itc(session)
    client = _client(session, Role.ACCOUNTANT)
    res = client.post(
        "/api/gst/ims/action",
        json={
            "action": "reject",
            "ids": [ids["matched"]],
            "confirm": True,
            "preview_token": "forged",
        },
    )
    assert res.status_code == 409
    assert "Nothing was changed" in res.json()["detail"]
    assert session.get(ItcRegister, ids["matched"]).ims_action is None


def test_ims_preview_then_confirm_commits_and_engine_recomputes(session):
    ids = _seed_itc(session)
    client = _client(session, Role.ACCOUNTANT)
    preview = client.post(
        "/api/gst/ims/action",
        json={"action": "reject", "ids": [ids["matched"]], "confirm": False},
    ).json()
    confirm = client.post(
        "/api/gst/ims/action",
        json={
            "action": "reject",
            "ids": [ids["matched"]],
            "confirm": True,
            "preview_token": preview["preview_token"],
        },
    )
    assert confirm.status_code == 200 and confirm.json()["committed"] is True
    assert session.get(ItcRegister, ids["matched"]).ims_action == "reject"

    # The stored ACTION drives a recomputed disposition — never a stored state.
    detail = client.get("/api/gst/detail").json()
    by_id = {r["id"]: r for r in detail["ims"]["invoices"]}
    rejected = by_id[str(ids["matched"])]
    assert rejected["state"] == "rejected" and rejected["itc_eligible"] is False
    # the rejected 18,000_00 is excluded from the engine's eligible-ITC aggregate
    assert detail["ims"]["eligible_itc_total"]["raw"] == 0


def test_ims_confirm_needs_write_ca_can_only_preview(session):
    ids = _seed_itc(session)
    client = _client(session, Role.CA)
    preview = client.post(
        "/api/gst/ims/action",
        json={"action": "accept", "ids": [ids["matched"]], "confirm": False},
    )
    assert preview.status_code == 200  # sizing up a write is reading
    confirm = client.post(
        "/api/gst/ims/action",
        json={
            "action": "accept",
            "ids": [ids["matched"]],
            "confirm": True,
            "preview_token": preview.json()["preview_token"],
        },
    )
    assert confirm.status_code == 403
    assert confirm.json()["detail"] == "missing capability: write"
    assert session.get(ItcRegister, ids["matched"]).ims_action is None


# ── (b) artifact downloads ────────────────────────────────────────────────────────


def _seed_invoice(session: Session) -> str:
    cust = Customer(
        name="Acme", state="KA", gstin="29AAAAA0000A1Z5",
        payment_terms=30, tds_applicable=0, tds_rate=0.0,
    )
    session.add(cust)
    session.flush()
    RevenueService().create_invoice(
        session,
        invoice_number="INV-9",
        customer_id=cust.id,
        invoice_date="2026-07-05",
        lines=[{"description": "svc", "quantity": 1, "rate": 100_000_00, "hsn_code": "9983"}],
        gst_rate=18,
    )
    session.commit()
    return "INV-9"


def test_gstr1_download_content_type_and_disposition(session):
    _seed_invoice(session)
    res = _client(session, Role.ACCOUNTANT).get("/api/gst/gstr1.json", params={"period": "2026-07"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert 'filename="gstr1-2026-07.json"' in res.headers["content-disposition"]
    assert res.json()["fp"] == "072026"


def test_einvoice_download_carries_the_draft_irn_label(session):
    inv = _seed_invoice(session)
    res = _client(session, Role.CA).get("/api/gst/einvoice.json", params={"invoice": inv})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    payload = res.json()
    # WS9.3: a locally computed IRN is DRAFT — the label is on the payload AND the QR caption.
    assert payload["IrnStatus"] == DRAFT_IRN_LABEL
    assert payload["QrData"]["Caption"] == DRAFT_IRN_LABEL

    missing = _client(session, Role.CA).get("/api/gst/einvoice.json", params={"invoice": "nope"})
    assert missing.status_code == 404


def test_downloads_denied_without_export_and_without_read(session):
    _seed_invoice(session)
    approver = _client(session, Role.APPROVER)  # read, no export
    for path, params in (
        ("/api/gst/gstr1.json", {"period": "2026-07"}),
        ("/api/gst/einvoice.json", {"invoice": "INV-9"}),
    ):
        res = approver.get(path, params=params)
        assert res.status_code == 403
        assert res.json()["detail"] == "missing capability: export"

    investor = _client(session, Role.INVESTOR)  # no read at all
    assert investor.get("/api/gst/detail").status_code == 403
