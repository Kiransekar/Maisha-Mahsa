"""P0-4 payroll run flow against the REAL Mahsa binary: preview → typed confirm → the run
lands in the EXISTING approvals queue → a decision releases it → artifacts download.

What each test is built to kill (mutation-proofing):
  · preview purity      — a preview that quietly calls ``run_payroll`` (row-count asserted 0),
                          and hardcoded badges: PF must be ``verified`` because the REAL engine
                          recomputed it to the paisa, while TDS/net must stay ◐ (unported).
  · typed confirm       — dropping the typed-phrase check (400, nothing written).
  · tamper              — skipping the confirm-token recomputation: a token minted over a
                          different month's preview must be refused 409 and write nothing.
  · approvals landing   — removing the ``payroll_run_pending`` metric, rule PAYROLL-005, or the
                          fold-driven queue wiring: a confirmed run MUST appear as a payroll
                          approval item citing PAYROLL-005.
  · release hook        — removing ``resolve_pending_runs`` (or its ``record_decision`` call):
                          an approvals decision must flip the draft run and clear the queue.
  · artifact RBAC/types — dropping the ``export`` gate (403 for Approver) or the content types
                          (application/pdf with a %PDF body; text/plain for the ECR).

RBAC over real signed JWTs for these routes is covered by test_rbac_matrix.py (rows added
there); this file overrides the one auth seam per role, the api_approvals.py precedent.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("MAISHA_DATABASE_URL", "sqlite://")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.audit import verify_chain  # noqa: E402
from app.core.audit_store import load_chain  # noqa: E402
from app.core.betterauth import get_principal  # noqa: E402
from app.core.entitlement_deps import SessionContext, get_session_context  # noqa: E402
from app.core.mahsa_client import MahsaClient  # noqa: E402
from app.core.money import Paise  # noqa: E402
from app.core.principal import Principal  # noqa: E402
from app.core.rbac import Role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models.payroll import Employee, PayrollEntry, PayrollRun  # noqa: E402
from app.db.session import get_session, session_factory  # noqa: E402
from app.deps import get_mahsa  # noqa: E402
from app.domains.payroll.service import PayrollService, compute_components  # noqa: E402
from app.web.api_approvals import router as approvals_router  # noqa: E402
from app.web.api_payroll import router as payroll_router  # noqa: E402

pytestmark = pytest.mark.integration

MONTH = "2026-06"


@pytest.fixture(autouse=True)
def _denial_audit_tables() -> None:
    """The 403 path chains the denial on rbac_deps' own global-engine session — make sure that
    engine has tables (the light per-test app never runs the real startup)."""
    Base.metadata.create_all(session_factory().kw["bind"])


def _client(session: Session, mahsa_url: str, role: Role = Role.OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(payroll_router)
    app.include_router(approvals_router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_mahsa] = lambda: MahsaClient(mahsa_url)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    # The entitlement layer resolves the plan straight off the verified token; this is its one
    # dependency seam (same idea as the get_principal override above).
    app.dependency_overrides[get_session_context] = lambda: SessionContext(
        org_id="org-7", org_plan="growth"
    )
    return TestClient(app)


def _seed_employee(session: Session) -> Employee:
    emp = Employee(
        employee_code="E1", name="Asha", date_of_joining="2021-04-01", state="MH", pan="AAAPA1234A"
    )
    session.add(emp)
    session.flush()
    PayrollService().set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    session.commit()
    return emp


def _fig(card: dict, suffix: str) -> dict:
    return next(f for f in card["figures"] if f["target"].endswith(suffix))


def _expected_comp() -> dict[str, int]:
    return compute_components(
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        lta=0,
        special_allowance=Paise.from_rupees(30000),
        state="MH",
        month=6,
        lop_days=0,
        days_in_month=30,
    )


# ── preview purity + live badges ─────────────────────────────────────────────────────────


def test_preview_badges_per_employee_and_mutates_nothing(session, mahsa_server) -> None:
    emp = _seed_employee(session)
    client = _client(session, mahsa_server)

    r = client.post("/api/payroll/runs/preview", json={"month_year": MONTH})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["mahsa_up"] is True and p["employee_count"] == 1

    card = p["employees"][0]
    assert card["employee_id"] == emp.id and card["name"] == "Asha"
    comp = _expected_comp()

    # §0.4: PF/ESI are ported targets — with the real engine up they verify to the paisa.
    pf = _fig(card, ".pf_employee")
    assert pf["value_paise"] == comp["employee_pf"]
    assert pf["state"] == "verified"
    assert _fig(card, ".esi_employee")["state"] == "verified"
    # TDS and net are NOT ported — they must read ◐ forever, never an optimistic ✓.
    assert _fig(card, ".tds")["state"] == "honest_pending"
    assert _fig(card, ".net_pay")["state"] == "honest_pending"
    assert _fig(card, ".net_pay")["value_paise"] == comp["net_salary"]
    assert p["verdict_hash"], "verified figures must be sealed into a verdict"
    assert p["confirm_phrase"] == MONTH and p["confirm_token"]

    # INVARIANT 9: the preview wrote NOTHING — no run, no entries, no audit seal.
    assert session.scalars(select(PayrollRun)).all() == []
    assert session.scalars(select(PayrollEntry)).all() == []


def test_preview_with_mahsa_down_is_honest_pending_everywhere(session) -> None:
    _seed_employee(session)
    client = _client(session, "http://127.0.0.1:9")  # dead port — Mahsa unreachable

    r = client.post("/api/payroll/runs/preview", json={"month_year": MONTH})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["mahsa_up"] is False
    for f in p["employees"][0]["figures"] + p["totals"]:
        assert f["state"] == "honest_pending", f  # never a fabricated ✓ with the gate down
    assert p["verdict_hash"] is None


# ── typed confirm + token tamper ─────────────────────────────────────────────────────────


def test_confirm_refuses_wrong_phrase_and_tampered_token(session, mahsa_server) -> None:
    _seed_employee(session)
    client = _client(session, mahsa_server)
    token = client.post("/api/payroll/runs/preview", json={"month_year": MONTH}).json()[
        "confirm_token"
    ]

    # Wrong typed phrase -> 400, nothing written.
    r = client.post(
        "/api/payroll/runs/confirm",
        json={"month_year": MONTH, "confirm_token": token, "confirm_text": "2099-01"},
    )
    assert r.status_code == 400
    assert session.scalars(select(PayrollRun)).all() == []

    # A token minted over a DIFFERENT preview (another month) -> 409, nothing written.
    r = client.post(
        "/api/payroll/runs/confirm",
        json={"month_year": "2026-07", "confirm_token": token, "confirm_text": "2026-07"},
    )
    assert r.status_code == 409
    assert "different preview" in r.json()["detail"]
    assert session.scalars(select(PayrollRun)).all() == []


# ── the whole loop: confirm → approvals queue → decision releases → artifacts ────────────


def test_confirmed_run_lands_in_approvals_and_decision_releases_it(
    session, mahsa_server
) -> None:
    emp = _seed_employee(session)
    client = _client(session, mahsa_server)
    p = client.post("/api/payroll/runs/preview", json={"month_year": MONTH}).json()

    r = client.post(
        "/api/payroll/runs/confirm",
        json={
            "month_year": MONTH,
            "confirm_token": p["confirm_token"],
            "confirm_text": MONTH,
            "trace_id": p["trace_id"],
        },
    )
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert receipt["status"] == "draft" and receipt["approval"]["queued"] is True

    run = session.scalars(select(PayrollRun)).one()
    assert run.status == "draft" and run.month_year == MONTH
    assert len(session.scalars(select(PayrollEntry)).all()) == 1

    # The audit seal is real, chained, and carries the previewed figures + trace id.
    chain = load_chain(session)
    recorded = [e for e in chain if e.action == "payroll.run_recorded"]
    assert len(recorded) == 1 and recorded[0].this_hash == receipt["audit_hash"]
    detail = json.loads(recorded[0].query)
    assert detail["trace_id"] == p["trace_id"] and detail["month_year"] == MONTH
    assert verify_chain(chain)

    # Artifact links come back per employee, pointing at the RBAC'd /api routes.
    per_emp = receipt["artifacts"]["per_employee"]
    assert per_emp[0]["employee_id"] == emp.id
    assert per_emp[0]["payslip"] == f"/api/payroll/employees/{emp.id}/payslip.pdf?period={MONTH}"
    assert per_emp[0]["form16"].endswith("form16.pdf?fy=2026-27")
    assert receipt["artifacts"]["ecr"] == f"/api/payroll/ecr.txt?period={MONTH}"

    # THE LANDING: the draft run makes the payroll fold yellow via PAYROLL-005, so the domain
    # appears in the EXISTING approvals queue (fold-driven — same queue HTMX renders).
    queue = client.get("/api/approvals").json()
    assert queue["mahsa_up"] is True
    payroll_items = [i for i in queue["items"] if i["domain"] == "payroll"]
    assert payroll_items, f"payroll missing from approvals queue: {queue['items']}"
    assert any(
        c["rule_id"] == "PAYROLL-005" for c in payroll_items[0]["citations"]
    ), payroll_items[0]["citations"]

    # The decision — recorded through the EXISTING decide route — releases the run.
    decided = client.post(
        "/api/approvals/payroll/decide",
        json={"decision": "approved", "confirm_text": "payroll"},
    )
    assert decided.status_code == 200, decided.text
    session.expire_all()
    assert session.scalars(select(PayrollRun)).one().status == "approved"

    # Released ⇒ the metric clears ⇒ payroll folds green ⇒ it leaves the queue.
    queue_after = client.get("/api/approvals").json()
    assert not [i for i in queue_after["items"] if i["domain"] == "payroll"]

    # The overview reflects the released run.
    overview = client.get("/api/payroll/runs/overview").json()
    assert overview["runs_pending_approval"] == 0
    assert overview["last_run"]["status"] == "approved"
    assert overview["employees"][0]["monthly_net_paise"] == _expected_comp()["net_salary"]


# ── artifacts: RBAC + content types ──────────────────────────────────────────────────────


def test_artifact_routes_are_export_gated_and_typed(session, mahsa_server) -> None:
    emp = _seed_employee(session)

    owner = _client(session, mahsa_server)
    payslip = owner.get(f"/api/payroll/employees/{emp.id}/payslip.pdf", params={"period": MONTH})
    assert payslip.status_code == 200
    assert payslip.headers["content-type"] == "application/pdf"
    assert payslip.content.startswith(b"%PDF")

    form16 = owner.get(f"/api/payroll/employees/{emp.id}/form16.pdf", params={"fy": "2026-27"})
    assert form16.status_code == 200
    assert form16.headers["content-type"] == "application/pdf"
    assert form16.content.startswith(b"%PDF")

    ecr = owner.get("/api/payroll/ecr.txt", params={"period": MONTH})
    assert ecr.status_code == 200
    assert ecr.headers["content-type"].startswith("text/plain")

    # Unknown employee is a 404, never a blank PDF.
    assert (
        owner.get("/api/payroll/employees/99999/payslip.pdf", params={"period": MONTH}).status_code
        == 404
    )

    # An Approver reads books but holds no `export` — a payslip is salary data leaving the app.
    approver = _client(session, mahsa_server, role=Role.APPROVER)
    denied = approver.get(
        f"/api/payroll/employees/{emp.id}/payslip.pdf", params={"period": MONTH}
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "missing capability: export"
