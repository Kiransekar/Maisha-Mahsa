"""P0-3 — Altitude-2 entry forms for the four highest-volume entities, on the P0-2 machinery.

Which mutation each test kills (INVARIANT 9 + §0.4):
  1. Preview mutates nothing for EVERY new action — kills dropping the dry-run rollback for
     a handler that writes through a real domain service (create_invoice writes 2 tables).
  2. The bill preview's TDS figures equal ``payables_calc.tds_on_payment``'s own output for a
     known input (₹60,000 @ 194J/company → 10% → ₹6,000) and the badge state comes from
     ``badge_state`` — kills re-implementing TDS math in the web layer or hardcoding a ✓.
  3. An unbalanced journal entry is a named 422 carrying both totals and writes nothing —
     kills dropping the double-entry validation from the journal handler.
  4. The invoice preview's GST split equals ``revenue_calc.compute_invoice`` for the same
     lines, intra vs inter state — kills deciding the split client-side or in the web layer.
  5. The salary-structure preview's PF/ESI/PT figures equal ``compute_components`` and the
     s.2(y) warning reuses ``check_ctc_compliance`` — kills recomputing components in the
     handler or dropping the compliance warning.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.mahsa_coverage import badge_state
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.ledger import ChartOfAccounts, JournalEntry
from app.db.models.payables import Bill, Vendor
from app.db.models.payroll import Employee, SalaryStructure
from app.db.models.revenue import Customer, Invoice
from app.db.models.shared import Company
from app.db.session import get_session
from app.domains.payables import payables_calc
from app.domains.payroll.service import compute_components
from app.domains.revenue import revenue_calc
from app.web.api_actions import router

pytestmark = pytest.mark.integration


def _seed(session: Session) -> None:
    """FK targets the entry forms point at. Supplier state Maharashtra → customer 1 is
    intra-state, customer 2 (Karnataka) is inter-state."""
    session.add(Company(id=1, name="Maisha Test Pvt Ltd", pan="AAACM1234A", state="Maharashtra"))
    session.add(Customer(id=1, name="Intra Co", state="Maharashtra"))
    session.add(Customer(id=2, name="Inter Co", state="Karnataka"))
    session.add(
        Vendor(id=1, name="Sharp Legal LLP", tds_section="194J", payee_type="company")
    )
    session.add(
        Employee(
            id=1, employee_code="E001", name="Asha Rao",
            date_of_joining="2026-01-05", state="Karnataka",
        )
    )
    session.add(ChartOfAccounts(id=1, code="1000", name="Cash", account_type="asset"))
    session.add(ChartOfAccounts(id=2, code="4000", name="Revenue", account_type="income"))
    # Commit — the preview dry-run ROLLS BACK the request session; seed rows must survive it.
    session.commit()


def _client(session: Session, role: Role = Role.OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    return TestClient(app, raise_server_exceptions=True)


def _count(session: Session, table) -> int:
    return session.scalar(select(func.count()).select_from(table)) or 0


INVOICE_LINES = [
    {"description": "Consulting — July", "quantity": "2", "rate": "10000"},
]
JOURNAL_LINES = [
    {"account_id": "1", "debit": "100", "credit": ""},
    {"account_id": "2", "debit": "", "credit": "100"},
]

# (domain, key) -> (the table the action writes, a valid form payload)
CASES = {
    ("revenue", "create-customer"): (
        Customer,
        {"name": "Acme Pvt Ltd", "state": "Maharashtra", "payment_terms": "45"},
    ),
    ("revenue", "create-invoice"): (
        Invoice,
        {"invoice_number": "INV-001", "customer_id": "1", "invoice_date": "2026-07-01",
         "gst_rate": "18", "lines": json.dumps(INVOICE_LINES)},
    ),
    ("payables", "create-vendor"): (
        Vendor,
        {"name": "New Vendor LLP", "tds_section": "194C", "payee_type": "individual"},
    ),
    ("payables", "create-bill"): (
        Bill,
        {"bill_number": "B-1042", "vendor_id": "1", "bill_date": "2026-07-01",
         "subtotal": "60000", "gst_amount": "10800"},
    ),
    ("ledger", "journal-entry"): (
        JournalEntry,
        {"entry_date": "2026-07-01", "description": "Cash sale",
         "lines": json.dumps(JOURNAL_LINES)},
    ),
    ("payroll", "add-employee"): (
        Employee,
        {"employee_code": "E002", "name": "Ravi Kumar", "date_of_joining": "2026-07-01",
         "state": "Karnataka"},
    ),
    ("payroll", "salary-structure"): (
        SalaryStructure,
        {"employee_id": "1", "effective_from": "2026-07-01", "basic": "50000",
         "hra": "20000"},
    ),
}


def test_preview_mutates_nothing_for_every_entry_form(session):
    """Kills: dropping the dry-run rollback for any of the seven new handlers."""
    _seed(session)
    client = _client(session)
    for (domain, key), (table, values) in CASES.items():
        before = _count(session, table)
        body = client.post(
            f"/api/domains/{domain}/actions/{key}/preview", json={"values": values}
        )
        assert body.status_code == 200, f"{domain}/{key}: {body.text}"
        data = body.json()
        assert data["committed"] is False
        assert data["will_create"]
        assert data["preview_token"]
        assert _count(session, table) == before, f"{domain}/{key} preview mutated the DB"


def test_preview_then_commit_creates_one_row_per_entry_form(session):
    _seed(session)
    client = _client(session)
    for (domain, key), (table, values) in CASES.items():
        before = _count(session, table)
        preview = client.post(
            f"/api/domains/{domain}/actions/{key}/preview", json={"values": values}
        ).json()
        body = client.post(
            f"/api/domains/{domain}/actions/{key}/commit",
            json={"values": values, "preview_token": preview["preview_token"]},
        )
        assert body.status_code == 200, f"{domain}/{key}: {body.text}"
        assert body.json()["committed"] is True
        assert _count(session, table) == before + 1, f"{domain}/{key} commit wrote nothing"


def test_bill_preview_tds_section_rate_amount_match_the_engine(session):
    """₹60,000 professional fees @ 194J (company payee): the engine says 10% → ₹6,000.
    Kills: re-implementing TDS in the web layer (any drift breaks the equality) and
    hardcoding the badge (state must equal what badge_state says for tds_on_payment)."""
    _seed(session)
    client = _client(session)
    figs = {
        f["key"]: f
        for f in client.post(
            "/api/domains/payables/actions/create-bill/preview",
            json={"values": CASES[("payables", "create-bill")][1]},
        ).json()["figures"]
    }
    engine = payables_calc.tds_on_payment("194J", 60000_00, payee_type="company")
    assert engine["tds_paise"] == 6000_00  # the known input's known answer, pinned
    assert figs["payables_tds_section"]["value"] == "194J"
    assert figs["payables_tds_rate"]["value"] == "10%"
    assert figs["tds_on_payment"]["raw"] == engine["tds_paise"]
    assert figs["tds_on_payment"]["state"] == badge_state("tds_on_payment")
    # Net payable = subtotal + GST - TDS, from the service's own return
    assert figs["payables_bill_net_paise"]["raw"] == 60000_00 + 10800_00 - 6000_00


def test_bill_below_threshold_deducts_nothing_and_says_why(session):
    """₹40,000 does not exceed the s.194J ₹50k threshold — no TDS, stated, not silent."""
    _seed(session)
    client = _client(session)
    data = client.post(
        "/api/domains/payables/actions/create-bill/preview",
        json={"values": {"bill_number": "B-1", "vendor_id": "1", "bill_date": "2026-07-01",
                         "subtotal": "40000"}},
    ).json()
    figs = {f["key"]: f for f in data["figures"]}
    assert figs["tds_on_payment"]["raw"] == 0
    assert "below the s.194J threshold" in data["will_create"]


def test_invoice_preview_gst_split_intra_vs_inter_matches_the_engine(session):
    """Same lines, two customers: Maharashtra→Maharashtra splits CGST+SGST; →Karnataka is
    IGST. Kills: computing the split anywhere but revenue_calc.compute_invoice."""
    _seed(session)
    client = _client(session)
    lines = [{"quantity": 2, "rate": 10000_00}]

    def preview_figs(customer_id: str) -> dict:
        values = {**CASES[("revenue", "create-invoice")][1], "customer_id": customer_id}
        r = client.post(
            "/api/domains/revenue/actions/create-invoice/preview", json={"values": values}
        )
        assert r.status_code == 200, r.text
        return {f["key"]: f for f in r.json()["figures"]}

    intra = preview_figs("1")
    engine_intra = revenue_calc.compute_invoice(lines, gst_rate=18.0, inter_state=False)
    assert intra["revenue_invoice_cgst_paise"]["raw"] == engine_intra["cgst_amount"]
    assert intra["revenue_invoice_sgst_paise"]["raw"] == engine_intra["sgst_amount"]
    assert "revenue_invoice_igst_paise" not in intra

    inter = preview_figs("2")
    engine_inter = revenue_calc.compute_invoice(lines, gst_rate=18.0, inter_state=True)
    assert inter["revenue_invoice_igst_paise"]["raw"] == engine_inter["igst_amount"]
    assert "revenue_invoice_cgst_paise" not in inter
    assert inter["revenue_invoice_total_paise"]["raw"] == engine_inter["total_amount"]


def test_journal_imbalance_is_a_named_422_and_writes_nothing(session):
    """Debits ₹100 vs credits ₹90 → explicit rejection naming BOTH totals (T6 template
    feeds ErrorState client-side). Kills: dropping the double-entry check."""
    _seed(session)
    client = _client(session)
    bad = [
        {"account_id": "1", "debit": "100", "credit": ""},
        {"account_id": "2", "debit": "", "credit": "90"},
    ]
    body = client.post(
        "/api/domains/ledger/actions/journal-entry/preview",
        json={"values": {"entry_date": "2026-07-01", "description": "Broken",
                         "lines": json.dumps(bad)}},
    )
    assert body.status_code == 422
    err = body.json()["detail"]["errors"][0]["error"]
    assert "does not balance" in err
    assert "₹100.00" in err and "₹90.00" in err
    assert body.json()["detail"]["note"] == "Nothing was changed."
    assert _count(session, JournalEntry) == 0


def test_journal_balanced_preview_shows_equal_badged_totals(session):
    _seed(session)
    client = _client(session)
    figs = {
        f["key"]: f
        for f in client.post(
            "/api/domains/ledger/actions/journal-entry/preview",
            json={"values": CASES[("ledger", "journal-entry")][1]},
        ).json()["figures"]
    }
    debit, credit = figs["ledger_journal_debit_paise"], figs["ledger_journal_credit_paise"]
    assert debit["raw"] == credit["raw"] == 100_00
    # §0.4: these are not Mahsa coverage targets, so they must read honest_pending, never ✓.
    assert figs["ledger_journal_debit_paise"]["state"] == "honest_pending"


def test_lines_rows_are_validated_per_column(session):
    """A row missing a required column is named field-precisely: lines[0].rate."""
    _seed(session)
    client = _client(session)
    values = {**CASES[("revenue", "create-invoice")][1],
              "lines": json.dumps([{"description": "x", "quantity": "1"}])}
    body = client.post(
        "/api/domains/revenue/actions/create-invoice/preview", json={"values": values}
    )
    assert body.status_code == 422
    assert any(e["field"] == "lines[0].rate" for e in body.json()["detail"]["errors"])


def test_salary_structure_preview_matches_compute_components_and_warns_on_s2y(session):
    """Basic ₹20k of ₹50k total (40% < 50%) — every statutory figure equals the payroll
    engine's own output and the s.2(y) warning from check_ctc_compliance is surfaced."""
    _seed(session)
    client = _client(session)
    values = {"employee_id": "1", "effective_from": "2026-07-01",
              "basic": "20000", "hra": "30000"}
    data = client.post(
        "/api/domains/payroll/actions/salary-structure/preview", json={"values": values}
    ).json()
    figs = {f["key"]: f for f in data["figures"]}
    engine = compute_components(
        basic=20000_00, hra=30000_00, lta=0, special_allowance=0,
        state="Karnataka", month=7,
    )
    assert figs["payroll_gross_paise"]["raw"] == engine["gross_salary"]
    assert figs["pf_employee"]["raw"] == engine["employee_pf"]
    assert figs["pf_employer"]["raw"] == engine["employer_pf"]
    assert figs["esi_employee"]["raw"] == engine["employee_esi"]
    assert figs["esi_employer"]["raw"] == engine["employer_esi"]
    assert figs["payroll_pt_paise"]["raw"] == engine["professional_tax"]
    assert figs["payroll_ctc_paise"]["raw"] == engine["ctc"]
    assert "WARNING" in data["will_create"] and "s.2(y)" in data["will_create"]
    # Every badge came through the one §0.4 gate — spot-check against the machinery itself.
    for key in ("pf_employee", "esi_employee"):
        assert figs[key]["state"] == badge_state(key)
    assert _count(session, SalaryStructure) == 0  # still a preview

    # And a compliant structure (Basic ₹50k of ₹70k ≈ 71%) carries no warning.
    ok = client.post(
        "/api/domains/payroll/actions/salary-structure/preview",
        json={"values": CASES[("payroll", "salary-structure")][1]},
    ).json()
    assert "WARNING" not in ok["will_create"]
