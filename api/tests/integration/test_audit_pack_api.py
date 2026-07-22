"""WS8.1 remainder — /api/audit/pack endpoints against the REAL Mahsa binary.

Pinned here (not shape-checking):
  1. RBAC: the pack is CA/audit-gated — VIEW_AUDIT for the JSON pack, EXPORT for the
     downloadable artifacts. An Approver (VIEW_AUDIT, no EXPORT) can read but not download;
     an Investor (no READ) gets nothing.
  2. Badge honesty end-to-end: a figure whose target Mahsa recomputes (TDS late fee u/s 234E)
     arrives ``verified``; an unported aggregate on the SAME return arrives ``honest_pending``.
  3. Mahsa unreachable → 503 that says so; no pack, no fabricated rules version.
  4. The artifacts embed the pack integrity hash on their cover.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.mahsa_client import MahsaClient
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains.tax.service import TaxService
from app.web.api_domains import router

pytestmark = pytest.mark.integration


def _client(session: Session, mahsa_url: str, role: Role) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_url)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    return TestClient(app)


def _seed_tds_return(session: Session) -> None:
    # Filed 10 days late → a real late_fee_234e figure computed by the tax service itself.
    TaxService().file_tds_return(
        session,
        return_type="24Q",
        quarter="2026-Q1",
        due_date="2026-07-31",
        filed_date="2026-08-10",
        total_deducted=250_000,
    )
    session.commit()


def test_ca_gets_full_pack_with_honest_badges(session, mahsa_server):
    _seed_tds_return(session)
    client = _client(session, mahsa_server, Role.CA)

    resp = client.get("/api/audit/pack")
    assert resp.status_code == 200
    pack = resp.json()
    assert set(pack["sections"]) == {
        "trial_balance", "profit_and_loss", "balance_sheet", "general_ledger",
        "statutory_registers", "form_26as_reconciliation", "msme_ageing",
    }
    assert pack["org_id"] == "org-7"  # bound to the session principal, not a request value
    assert pack["rules_version"]  # from the live engine's /health
    assert len(pack["integrity"]["hash"]) == 64

    regs = pack["sections"]["statutory_registers"]
    late_fee = next(f for f in regs if "Late Filing Fee u/s 234E" in f["label"])
    deducted = next(f for f in regs if "Tax Deducted" in f["label"])
    assert late_fee["badge"] == "verified"  # Mahsa-ported target (late_fee_234e)
    assert deducted["badge"] == "honest_pending"  # unported aggregate: never fabricated
    # No 26AS statement loaded → stated, not silently "reconciled".
    assert "No Form 26AS statement loaded" in pack["section_notes"]["form_26as_reconciliation"]


def test_artifacts_download_and_embed_the_pack_hash(session, mahsa_server):
    _seed_tds_return(session)
    client = _client(session, mahsa_server, Role.CA)
    pack = client.get("/api/audit/pack").json()

    z = client.get("/api/audit/pack.zip")
    assert z.status_code == 200
    assert z.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        cover = list(csv.reader(io.StringIO(zf.read("00_cover.csv").decode("utf-8"))))
    assert ["Integrity hash (SHA-256)", pack["integrity"]["hash"]] in cover

    p = client.get("/api/audit/pack.pdf")
    assert p.status_code == 200
    assert p.headers["content-type"] == "application/pdf"
    assert p.content.startswith(b"%PDF")


def test_approver_can_view_pack_but_not_export_artifacts(session, mahsa_server):
    client = _client(session, mahsa_server, Role.APPROVER)
    assert client.get("/api/audit/pack").status_code == 200  # has VIEW_AUDIT
    assert client.get("/api/audit/pack.zip").status_code == 403  # no EXPORT
    assert client.get("/api/audit/pack.pdf").status_code == 403


def test_investor_gets_no_pack_at_all(session):
    client = _client(session, "http://127.0.0.1:9", Role.INVESTOR)
    # Fails closed at the router's READ baseline — before Mahsa is ever consulted.
    assert client.get("/api/audit/pack").status_code == 403


def test_mahsa_down_is_a_stated_503_not_a_fabricated_pack(session):
    client = _client(session, "http://127.0.0.1:9", Role.CA)  # nothing listening
    resp = client.get("/api/audit/pack")
    assert resp.status_code == 503
    assert "unreachable" in resp.json()["detail"]
