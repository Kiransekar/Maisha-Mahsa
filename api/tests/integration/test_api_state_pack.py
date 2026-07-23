"""WS2.3 — /api/payroll/state-pack/{state}: PT computed THROUGH the pack path with citation,
not-applicable honesty, and 409 refusal for BLOCKED-CA items."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Role
from app.web.api_payroll import router

pytestmark = pytest.mark.integration


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    return TestClient(app)


def test_mh_pt_computes_through_pack_with_citation() -> None:
    r = _client().get(
        "/api/payroll/state-pack/MH", params={"gross_monthly_paise": 2_000_000, "month": 2}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["monthly"] == {"status": "computed", "amount_paise": 30000, "note": None}
    pt = body["pt"]
    assert pt["pt_status"] == "monthly"
    assert pt["citation_url"].startswith("https://www.mahagst.gov.in/")
    assert pt["pack_version"] == "2026.07.1" and len(pt["pack_sha256"]) == 64


def test_tn_half_yearly_computes_and_madurai_refuses_409() -> None:
    c = _client()
    ok = c.get(
        "/api/payroll/state-pack/TN",
        params={"half_yearly_income_paise": 5_000_000, "jurisdiction": "chennai_corporation"},
    )
    assert ok.status_code == 200
    assert ok.json()["half_yearly"]["amount_paise"] == 51000
    blocked = c.get(
        "/api/payroll/state-pack/TN",
        params={"half_yearly_income_paise": 5_000_000, "jurisdiction": "madurai_corporation"},
    )
    assert blocked.status_code == 409
    assert "BLOCKED-CA" in blocked.json()["detail"]


def test_dl_renders_not_applicable_never_a_zero() -> None:
    r = _client().get(
        "/api/payroll/state-pack/DL", params={"gross_monthly_paise": 2_000_000, "month": 6}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pt"]["pt_status"] == "not_applicable"
    assert body["monthly"]["status"] == "not_applicable"
    assert body["monthly"]["amount_paise"] is None
