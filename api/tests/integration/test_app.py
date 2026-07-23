"""App-level integration: the FastAPI surface renders and reports health. Uses an
in-memory DB; does not require the Mahsa sidecar."""

import os

import pytest

# Must be set before importing app.main (module instantiates the app at import time).
os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.betterauth import TOKEN_COOKIE, get_principal  # noqa: E402
from app.core.principal import Principal  # noqa: E402
from app.core.rbac import Role  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _act_as_owner(betterauth_owner_env):
    """P2-6: the legacy password login is deleted, so the middleware is satisfied the way the
    HTMX surface is in production — a real signed owner JWT in the `maisha_jwt` cookie (the
    `betterauth_owner_env` JWKS fixture). This file tests page/flow semantics, not RBAC, so it
    still overrides the one auth seam with an Owner — the same blessed pattern as
    test_api_bulk.py; RBAC itself is proven over real signed tokens in test_rbac_matrix.py.
    Module-scoped and popped on the way out so it can never leak into that file."""
    client.cookies.set(TOKEN_COOKIE, betterauth_owner_env.token)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u-owner", org_id="org-7", role=Role.OWNER, email="owner@example.com"
    )
    yield
    client.cookies.delete(TOKEN_COOKIE)
    app.dependency_overrides.pop(get_principal, None)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_dashboard_renders_all_domain_cards():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Domain Health" in body
    # every domain appears as a card
    for d in ("treasury", "payroll", "gst", "vault"):
        assert d in body
    # all 12 domains are now implemented -> none render with the "pending" pill
    assert "pill--pending" not in body
    # KPI strip + panels render (degrades without Mahsa)
    assert "Compliance Calendar" in body
    assert "Approvals Pending" in body
    # the Ask Maisha bar is present on every page
    assert 'id="ask-input"' in body


def test_domain_page_renders():
    resp = client.get("/d/gst")
    assert resp.status_code == 200
    body = resp.text
    assert "Figures" in body
    assert "gst" in body.lower()


def test_unknown_domain_404():
    assert client.get("/d/not-a-domain").status_code == 404


def test_ask_page_empty_shows_suggestions():
    resp = client.get("/ask")
    assert resp.status_code == 200
    assert "Try asking" in resp.text


def test_ask_page_with_query_degrades_to_facts():
    # No Mahsa, LLM off -> deterministic figures, flagged offline.
    resp = client.get("/ask", params={"q": "what's our runway?"})
    assert resp.status_code == 200
    body = resp.text
    assert "deterministic figures" in body
    assert "treasury" in body.lower()


def test_ask_post_returns_answer_card():
    resp = client.post("/ask", data={"q": "any MSME payments overdue?"})
    assert resp.status_code == 200
    body = resp.text
    assert "answer__prov" in body  # the answer-card partial rendered
    assert "payables" in body.lower()


def test_action_bar_appears_on_domain_with_actions():
    body = client.get("/d/ledger").text
    assert "Create account" in body  # action bar rendered


def test_action_form_renders():
    resp = client.get("/d/ledger/action/create-account/form")
    assert resp.status_code == 200
    assert 'name="code"' in resp.text


def test_action_submit_persists_and_refreshes():
    resp = client.post(
        "/d/vault/action/ingest",
        data={"file_name": "msa.pdf", "content": "acme agreement", "upload_date": "2026-05-10"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "ingested" in body  # success message / toast
    assert 'id="figures"' in body  # out-of-band figures refresh included


def test_action_submit_bad_input_re_renders_form_with_error():
    # shares_held must be an int; a non-numeric value should re-render the form with an error.
    resp = client.post(
        "/d/equity/action/add-shareholder",
        data={"name": "X", "category": "founder", "shares_held": "not-a-number"},
    )
    assert resp.status_code == 200
    assert "drawer__err" in resp.text


def test_unknown_action_404():
    assert client.get("/d/ledger/action/nope/form").status_code == 404


def test_approvals_page_renders():
    resp = client.get("/approvals")
    assert resp.status_code == 200
    assert "Approvals" in resp.text
    # Mahsa is down in tests -> degraded message, page still renders
    assert "Mahsa sidecar offline" in resp.text


def test_approvals_decide_degrades_without_mahsa():
    resp = client.post("/approvals/gst/decide", data={"decision": "approved"})
    assert resp.status_code == 200
    assert "Mahsa offline" in resp.text  # decision not recorded, surfaced honestly


def test_cfo_page_renders():
    resp = client.get("/cfo")
    assert resp.status_code == 200
    body = resp.text
    assert "CFO Strategy" in body
    assert "Scenario engine" in body
    assert "Cap table" in body


def test_cfo_scenario_returns_result():
    resp = client.post("/cfo/scenario", data={"revenue_mult": "1.2", "extra_cost": "0"})
    assert resp.status_code == 200
    assert "Runway" in resp.text


def test_investor_page_renders():
    resp = client.get("/investor")
    assert resp.status_code == 200
    assert "Investor Update" in resp.text
    assert "Highlights" in resp.text


def test_investor_preview_includes_highlights():
    resp = client.post(
        "/investor/preview", data={"highlights": "Closed 3 logos\nBurn multiple 1.4"}
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Closed 3 logos" in body and "Burn multiple 1.4" in body


def test_investor_send_degrades_without_smtp():
    resp = client.post("/investor/send", data={"highlights": "x"})
    assert resp.status_code == 200
    assert "Could not send" in resp.text or "sent to" in resp.text


def test_cfo_investor_send_degrades_without_smtp():
    resp = client.post("/cfo/investor/send", data={})
    assert resp.status_code == 200
    # MailHog isn't running in tests -> surfaced, not raised
    assert "Could not send" in resp.text or "sent to" in resp.text


def test_payslip_and_form16_pdf_download():
    # seed an employee + salary structure via the API, then download the statutory PDFs
    emp = client.post(
        "/api/payroll/employees",
        json={
            "employee_code": "PSE1",
            "name": "Asha",
            "date_of_joining": "2021-04-01",
            "state": "MH",
            "pan": "ABCDE1234F",
        },
    )
    assert emp.status_code in (200, 201)
    eid = emp.json()["employee_id"] if "employee_id" in emp.json() else emp.json().get("id")
    salary = client.post(
        f"/api/payroll/employees/{eid}/salary",
        json={
            "effective_from": "2026-04-01",
            "basic": 5000000,
            "hra": 2000000,
            "special_allowance": 3000000,
        },
    )
    assert salary.status_code in (200, 201)

    payslip = client.get(f"/d/payroll/{eid}/payslip", params={"period": "2026-06"})
    assert payslip.status_code == 200
    assert payslip.headers["content-type"] == "application/pdf"
    assert payslip.content[:5] == b"%PDF-"

    form16 = client.get(f"/d/payroll/{eid}/form16", params={"fy": "2026-27"})
    assert form16.status_code == 200
    assert form16.content[:5] == b"%PDF-"

    ecr = client.get("/d/payroll/ecr.txt", params={"period": "2026-06"})
    assert ecr.status_code == 200
    assert ecr.headers["content-type"].startswith("text/plain")
    assert "#~#" in ecr.text  # EPFO ECR delimiter


def test_ocr_routes_degrade_to_503_without_tesseract():
    # CI has no tesseract binary -> the OCR endpoints surface 503 (graceful), not 500.
    from app.core import ocr

    if ocr.tesseract_available():
        return  # environment has OCR; degradation path N/A
    r1 = client.post("/d/expense/ocr-receipt", files={"file": ("r.png", b"x", "image/png")})
    assert r1.status_code == 503
    r2 = client.post(
        "/d/vault/ocr-ingest",
        files={"file": ("s.png", b"x", "image/png")},
        data={"upload_date": "2026-05-10"},
    )
    assert r2.status_code == 503


def test_expense_ocr_json_route_reuses_the_same_handler_as_the_htmx_route():
    """P1-8: /api/expense/ocr-receipt is a thin wrapper over ExpenseService.ocr_capture — the
    SAME call the HTMX /d/expense/ocr-receipt route makes. Same bytes in -> identical outcome,
    proving there is exactly one parser, never a second implementation that could drift."""
    from app.core import ocr

    if ocr.tesseract_available():
        return  # environment has OCR; both routes would 200 with parsed fields instead
    photo = ("receipt.png", b"not a real image", "image/png")
    htmx = client.post("/d/expense/ocr-receipt", files={"file": photo})
    api_json = client.post("/api/expense/ocr-receipt", files={"file": photo})
    assert htmx.status_code == api_json.status_code == 503
    assert htmx.json()["detail"] == api_json.json()["detail"]


def test_payslip_unknown_employee_404():
    assert client.get("/d/payroll/99999/payslip", params={"period": "2026-06"}).status_code == 404


def test_gstr1_json_export_downloads():
    # seed a customer + posted invoice via the API, then export the GSTN-schema JSON
    cust = client.post(
        "/api/revenue/customers",
        json={"name": "Acme", "state": "MH", "gstin": "27AAPFU0939F1ZV"},
    )
    assert cust.status_code in (200, 201)
    cid = cust.json().get("customer_id") or cust.json().get("id")
    inv = client.post(
        "/api/revenue/invoices",
        json={
            "invoice_number": "JEXP-1",
            "customer_id": cid,
            "invoice_date": "2026-05-10",
            "lines": [{"description": "svc", "quantity": 1, "rate": 10000000, "hsn_code": "9983"}],
            "gst_rate": 18,
        },
    )
    assert inv.status_code in (200, 201)

    resp = client.get("/d/gst/gstr1.json", params={"period": "2026-05"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    payload = resp.json()
    assert payload["fp"] == "052026"
    assert payload["b2b"][0]["ctin"] == "27AAPFU0939F1ZV"

    # the same invoice can be turned into an e-invoice (IRN + NIC payload)
    einv = client.get("/d/gst/einvoice.json", params={"invoice": "JEXP-1"})
    assert einv.status_code == 200
    ep = einv.json()
    assert len(ep["Irn"]) == 64 and ep["DocDtls"]["No"] == "JEXP-1"
    assert ep["QrData"]["Irn"] == ep["Irn"]


def test_einvoice_unknown_invoice_404():
    assert client.get("/d/gst/einvoice.json", params={"invoice": "NOPE-1"}).status_code == 404


def test_audit_page_renders_and_verifies_chain():
    resp = client.get("/audit")
    assert resp.status_code == 200
    body = resp.text
    assert "Audit &amp; Trace" in body
    assert "CHAIN INTACT" in body  # empty/clean chain verifies
    assert "LLM trace" in body


# ── final coverage sweep: every screen renders ──────────────────────────────────────

ALL_DOMAINS = (
    "treasury",
    "revenue",
    "payables",
    "expense",
    "payroll",
    "gst",
    "tax",
    "compliance",
    "ledger",
    "forecast",
    "equity",
    "vault",
)


@pytest.mark.parametrize("domain", ALL_DOMAINS)
def test_every_domain_page_renders(domain):
    resp = client.get(f"/d/{domain}")
    assert resp.status_code == 200
    assert "Figures" in resp.text
    assert "ask-input" in resp.text  # the global Ask bar is on every page


@pytest.mark.parametrize("path", ["/", "/ask", "/approvals", "/cfo", "/audit"])
def test_every_top_level_page_renders(path):
    resp = client.get(path)
    assert resp.status_code == 200
    # the metallic theme + nav chrome are present on every page
    assert "Maisha-Mahsa" in resp.text
    assert "/static/css/app.css" in resp.text


def test_parallel_run_start_and_observe_flow():
    # fresh app DB: no active run -> the start CTA is shown
    page = client.get("/parallel")
    assert page.status_code == 200
    assert "Start 30-day parallel run" in page.text

    # start the run (redirects back to /parallel)
    started = client.post("/parallel/start", data={"name": "Test run"})
    assert started.status_code == 200  # TestClient follows the 303 redirect
    assert "Readiness" in started.text

    # capture Maisha's figures, then record a matching external figure -> reconciles ✓
    client.post("/history/capture")
    obs = client.post(
        "/parallel/observe",
        data={"domain": "gst", "metric": "gstr3b_days_late", "external_value": "0"},
    )
    assert obs.status_code == 200
    assert "Reconciliation" in obs.text or "gstr3b_days_late" in obs.text


def test_capture_then_domain_trend_renders():
    # two captures -> the domain page shows real sparkline trends (no fabricated data).
    assert client.post("/history/capture").status_code == 200
    assert client.post("/history/capture").status_code == 200
    resp = client.get("/d/gst")
    assert resp.status_code == 200
    body = resp.text
    assert "Trends" in body
    assert "<svg" in body and "captures" in body


# ── SPA JSON API (frontend/) ──────────────────────────────────────────────────
# The React SPA reads the SAME assemblers the HTMX pages render. Mahsa is absent in this
# module, so these also pin the honest-degradation contract: 200 + mahsa_up:false and an
# empty view — never a figure that looks verified without a live recompute gate.
def test_api_today_json_shape_and_honest_degradation():
    resp = client.get("/api/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mahsa_up"] is False  # no sidecar in this module
    assert set(body) >= {"as_of", "cash_strip", "needs_you", "trouble", "penalties_avoided"}
    # every cash figure is honest-pending, never a fabricated ✓ (WS7.1 T1 invariant)
    assert body["cash_strip"], "cash strip must render its panels"
    assert all(p["state"] == "honest_pending" for p in body["cash_strip"])
    assert body["needs_you"] == []  # approvals need Mahsa; honest-empty, not invented


def test_api_inbox_json_shape_and_honest_degradation():
    resp = client.get("/api/inbox")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mahsa_up"] is False
    assert body["items"] == []  # honest-empty without the recompute gate
    # all five queues are still described so the SPA can render honest empty states
    keys = [q["key"] for q in body["queues"]]
    assert len(keys) == 5 and "awaiting_approval" in keys and "mahsa_blocked" in keys
    assert all("empty" in q and "label" in q for q in body["queues"])
