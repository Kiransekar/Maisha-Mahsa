"""F3 — the web action layer. A declarative registry of domain actions the UI renders as a
drawer form and POSTs to. Handlers call the existing domain services directly (the JSON
``/api/*`` routes stay untouched) and return a short status message for the toast.

Money fields are entered in rupees and converted to exact paise here at the edge. Adding an
action is config: declare its fields + a handler; the drawer, routing and toast are generic.

P0-3 (Altitude-2 entry forms): a handler may also return ``(message, figures)`` where
``figures`` are engine-computed badged figures (GST split, TDS deducted, CTC breakdown…)
taken from the SERVICE's own return value — never a re-computation that could drift — and
badged only through ``mahsa_coverage.badge_state`` (§0.4: unknown falls to honest_pending,
a fabricated ✓ is impossible by construction). ``type="lines"`` fields carry a canonical
JSON array of rows validated per the ``columns`` sub-schema.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.mahsa_coverage import badge_state
from app.core.money import Paise
from app.db.models.payables import Vendor
from app.db.models.payroll import Employee
from app.db.models.revenue import Customer
from app.domains.compliance.service import ComplianceService
from app.domains.equity.service import EquityService
from app.domains.expense.service import ExpenseService
from app.domains.ledger.service import LedgerService
from app.domains.payables import payables_calc
from app.domains.payables.service import PayablesService
from app.domains.payroll.service import PayrollService, check_ctc_compliance
from app.domains.revenue.service import RevenueService
from app.domains.vault.service import VaultService


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str = "text"  # text | number | date | select | lines
    required: bool = True
    placeholder: str = ""
    options: tuple[str, ...] = ()
    columns: tuple[Field, ...] = ()  # sub-schema for type == "lines"


@dataclass(frozen=True)
class Action:
    domain: str
    key: str
    label: str
    fields: tuple[Field, ...]
    handler: Callable[[Session, dict[str, str]], str | tuple[str, list[dict[str, Any]]]]


# ── badged-figure helpers (the ONE §0.4 gate; never a hardcoded state) ─────────────


def _money_fig(key: str, label: str, paise: int) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": Paise.from_paise(paise).format_inr(),
        "raw": int(paise),
        "state": badge_state(key),
    }


def _text_fig(key: str, label: str, value: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "raw": value, "state": badge_state(key)}


# ── handlers ──────────────────────────────────────────────────────────────────────

def _create_account(session: Session, d: dict[str, str]) -> str:
    LedgerService().create_account(
        session, code=d["code"], name=d["name"], account_type=d["account_type"]
    )
    return f"Account {d['code']} — {d['name']} created."


def _add_deadline(session: Session, d: dict[str, str]) -> str:
    ComplianceService().add_deadline(
        session,
        domain=d["domain"],
        form_name=d["form_name"],
        due_date=d["due_date"],
        filing_period=d.get("filing_period") or None,
    )
    return f"Deadline '{d['form_name']}' added (due {d['due_date']})."


def _add_shareholder(session: Session, d: dict[str, str]) -> str:
    shares = int(d["shares_held"])
    EquityService().add_shareholder(
        session, name=d["name"], category=d["category"], shares_held=shares
    )
    return f"Shareholder {d['name']} ({shares:,} shares) added."


def _submit_claim(session: Session, d: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    # ponytail: ExpenseClaim has no dedicated GSTIN column — the OCR-parsed GSTIN (P1-8) folds
    # into the free-text `description` rather than a schema migration; add a real column when
    # expense claims need to reconcile against a vendor's ITC.
    gstin = (d.get("vendor_gstin") or "").strip()
    description = f"GSTIN {gstin}" if gstin else None
    result = ExpenseService().submit_claim(
        session,
        claim_date=d["claim_date"],
        expense_date=d["expense_date"],
        category=d["category"],
        amount=Paise.from_rupees(d["amount"]),
        description=description,
    )
    msg = f"Expense claim ₹{d['amount']} ({d['category']}) submitted."
    if result["over_policy"]:
        limit_text = (
            Paise.from_paise(result["policy_limit"]).format_inr()
            if result["policy_limit"] is not None
            else "no set limit"
        )
        msg += (
            f" WARNING — over the {d['category']} policy limit ({limit_text}) by "
            f"{Paise.from_paise(result['excess']).format_inr()}; needs approval before "
            "reimbursement."
        )
    return (msg, [])


def _ingest_document(session: Session, d: dict[str, str]) -> str:
    VaultService().ingest(
        session, file_name=d["file_name"], content=d["content"], upload_date=d["upload_date"]
    )
    return f"Document '{d['file_name']}' ingested."


# ── P0-3 entry-form handlers (figures come from the service's OWN return value) ────


def _create_customer(session: Session, d: dict[str, str]) -> str:
    cust = Customer(
        name=d["name"],
        gstin=d.get("gstin") or None,
        state=d.get("state") or None,
        payment_terms=int(d.get("payment_terms") or 30),
    )
    session.add(cust)
    session.flush()
    return (
        f"Customer {cust.name} (id {cust.id}) created — "
        f"place of supply: {cust.state or 'not set (invoices default to intra-state)'}."
    )


def _create_invoice(session: Session, d: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    rows = json.loads(d["lines"])
    lines = [
        {
            "description": r.get("description", ""),
            "quantity": int(r["quantity"]),
            "rate": int(Paise.from_rupees(r["rate"])),
        }
        for r in rows
    ]
    res = RevenueService().create_invoice(
        session,
        invoice_number=d["invoice_number"],
        customer_id=int(d["customer_id"]),
        invoice_date=d["invoice_date"],
        lines=lines,
        gst_rate=float(d.get("gst_rate") or 18),
    )
    inter = int(res["igst_amount"]) > 0
    figs = [_money_fig("revenue_invoice_subtotal_paise", "Taxable value", res["subtotal"])]
    if inter:
        figs.append(
            _money_fig("revenue_invoice_igst_paise", "IGST (inter-state)", res["igst_amount"])
        )
    else:
        figs.append(
            _money_fig("revenue_invoice_cgst_paise", "CGST (intra-state)", res["cgst_amount"])
        )
        figs.append(
            _money_fig("revenue_invoice_sgst_paise", "SGST (intra-state)", res["sgst_amount"])
        )
    figs.append(_money_fig("revenue_invoice_total_paise", "Invoice total", res["total_amount"]))
    if int(res["tds_amount"]) > 0:
        figs.append(
            _money_fig("revenue_invoice_tds_paise", "TDS the customer deducts", res["tds_amount"])
        )
        figs.append(
            _money_fig("revenue_invoice_net_paise", "Net receivable", res["net_receivable"])
        )
    split = "inter-state (IGST)" if inter else "intra-state (CGST + SGST)"
    return (
        f"Invoice {res['invoice_number']} ({len(lines)} lines) — {split}, due {res['due_date']}.",
        figs,
    )


def _create_vendor(session: Session, d: dict[str, str]) -> str:
    section = d.get("tds_section") or None
    vendor = Vendor(
        name=d["name"],
        gstin=d.get("gstin") or None,
        tds_section=section,
        payee_type=d.get("payee_type") or "company",
        payment_terms=int(d.get("payment_terms") or 30),
        msme_status=1 if d.get("msme_type") else 0,
        msme_type=d.get("msme_type") or None,
    )
    session.add(vendor)
    session.flush()
    tds_note = (
        f"TDS s.{section} will be deducted on bills above the threshold"
        if section
        else "no TDS section — nothing will be deducted"
    )
    return f"Vendor {vendor.name} (id {vendor.id}) created — {tds_note}."


def _create_bill(session: Session, d: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    vendor = session.get(Vendor, int(d["vendor_id"]))
    if vendor is None:
        raise ValueError(f"vendor {d['vendor_id']} not found")
    res = PayablesService().create_bill(
        session,
        bill_number=d["bill_number"],
        vendor_id=vendor.id,
        bill_date=d["bill_date"],
        subtotal=int(Paise.from_rupees(d["subtotal"])),
        gst_amount=int(Paise.from_rupees(d.get("gst_amount") or "0")),
    )
    figs: list[dict[str, Any]] = []
    msg = f"Bill {res['bill_number']} — due {res['due_date']}"
    if vendor.tds_section:
        # Section + rate from the SAME engine config create_bill used; amount from its result.
        rate = payables_calc.tds_rate(vendor.tds_section, payee_type=vendor.payee_type)
        figs.append(_text_fig("payables_tds_section", "TDS section", vendor.tds_section))
        figs.append(_text_fig("payables_tds_rate", "TDS rate", f"{rate}%"))
        figs.append(_money_fig("tds_on_payment", "TDS deducted", res["tds_amount"]))
        if int(res["tds_amount"]) == 0:
            msg += f" (below the s.{vendor.tds_section} threshold — no TDS arises)"
    figs.append(
        _money_fig("payables_bill_net_paise", "Net payable (after TDS)", res["total_amount"])
    )
    return (msg + ".", figs)


def _journal_entry(session: Session, d: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    rows = json.loads(d["lines"])
    lines = [
        {
            "account_id": int(r["account_id"]),
            "debit": int(Paise.from_rupees(r.get("debit") or "0")),
            "credit": int(Paise.from_rupees(r.get("credit") or "0")),
            "description": r.get("description") or None,
        }
        for r in rows
    ]
    total_debit = sum(int(ln["debit"] or 0) for ln in lines)
    total_credit = sum(int(ln["credit"] or 0) for ln in lines)
    if total_debit != total_credit:
        # Named, exact rejection (T6): what happened and by how much — the service's own
        # is_balanced check backstops this; nothing is written on either path.
        raise ValueError(
            "Journal entry does not balance: total debits "
            f"{Paise.from_paise(total_debit).format_inr()} ≠ total credits "
            f"{Paise.from_paise(total_credit).format_inr()}. Fix the lines so both sides match."
        )
    res = LedgerService().post_journal_entry(
        session, entry_date=d["entry_date"], description=d["description"], lines=lines
    )
    figs = [
        _money_fig("ledger_journal_debit_paise", "Total debits", res["total_debit"]),
        _money_fig("ledger_journal_credit_paise", "Total credits", res["total_credit"]),
    ]
    return (f"Journal entry ({len(lines)} lines) dated {d['entry_date']} posted.", figs)


def _add_employee(session: Session, d: dict[str, str]) -> str:
    emp = Employee(
        employee_code=d["employee_code"],
        name=d["name"],
        date_of_joining=d["date_of_joining"],
        state=d.get("state") or None,
        pan=d.get("pan") or None,
    )
    session.add(emp)
    session.flush()
    return f"Employee {emp.employee_code} — {emp.name} (id {emp.id}) added."


def _salary_structure(session: Session, d: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    structure = PayrollService().set_salary_structure(
        session,
        int(d["employee_id"]),
        effective_from=d["effective_from"],
        basic=int(Paise.from_rupees(d["basic"])),
        hra=int(Paise.from_rupees(d.get("hra") or "0")),
        lta=int(Paise.from_rupees(d.get("lta") or "0")),
        special_allowance=int(Paise.from_rupees(d.get("special_allowance") or "0")),
    )
    figs = [
        _money_fig("payroll_gross_paise", "Gross / month", structure.gross_salary),
        _money_fig("pf_employee", "PF — employee", structure.employee_pf),
        _money_fig("pf_employer", "PF — employer", structure.employer_pf),
        _money_fig("esi_employee", "ESI — employee", structure.employee_esi),
        _money_fig("esi_employer", "ESI — employer", structure.employer_esi),
        _money_fig("payroll_pt_paise", "Professional tax", structure.professional_tax),
        _money_fig("payroll_net_paise", "Net / month", structure.net_salary),
        _money_fig("payroll_ctc_paise", "CTC / month", structure.ctc),
    ]
    report = check_ctc_compliance(
        basic=structure.basic,
        hra=structure.hra,
        lta=structure.lta,
        special_allowance=structure.special_allowance,
    )
    msg = f"Salary structure effective {d['effective_from']} set for employee {d['employee_id']}."
    if not report["compliant"]:
        msg += (
            " WARNING — Code on Wages s.2(y): Basic "
            f"{Paise.from_paise(report['basic_plus_da']).format_inr()} is below the required "
            f"minimum {Paise.from_paise(report['required_minimum_basic_plus_da']).format_inr()} "
            "(50% of total remuneration)."
        )
    return (msg, figs)


# ── registry ──────────────────────────────────────────────────────────────────────

_ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
_SHAREHOLDER_CATS = ("founder", "investor", "esop", "advisor")
_TDS_SECTIONS = ("194C", "194J", "194H", "194I")
_PAYEE_TYPES = ("individual", "huf", "company")
_MSME_TYPES = ("micro", "small", "medium")

ACTIONS: dict[str, list[Action]] = {
    "ledger": [
        Action("ledger", "create-account", "Create account", (
            Field("code", "Account code", placeholder="1000"),
            Field("name", "Name", placeholder="Cash"),
            Field("account_type", "Type", type="select", options=_ACCOUNT_TYPES),
        ), _create_account),
        Action("ledger", "journal-entry", "Journal entry", (
            Field("entry_date", "Entry date", type="date"),
            Field("description", "Narration", placeholder="Office rent for July"),
            Field("lines", "Lines", type="lines", columns=(
                Field("account_id", "Account ID", type="number", placeholder="1"),
                Field("debit", "Debit (₹)", type="number", required=False, placeholder="0"),
                Field("credit", "Credit (₹)", type="number", required=False, placeholder="0"),
                Field("description", "Line narration", required=False),
            )),
        ), _journal_entry),
    ],
    "revenue": [
        Action("revenue", "create-customer", "New customer", (
            Field("name", "Name", placeholder="Acme Pvt Ltd"),
            Field("state", "State (place of supply)", required=False, placeholder="Maharashtra"),
            Field("gstin", "GSTIN", required=False, placeholder="27AAAAA0000A1Z5"),
            Field("payment_terms", "Payment terms (days)", type="number", required=False,
                  placeholder="30"),
        ), _create_customer),
        Action("revenue", "create-invoice", "New invoice", (
            Field("invoice_number", "Invoice number", placeholder="INV-001"),
            Field("customer_id", "Customer ID", type="number", placeholder="1"),
            Field("invoice_date", "Invoice date", type="date"),
            Field("gst_rate", "GST rate (%)", type="number", required=False, placeholder="18"),
            Field("lines", "Line items", type="lines", columns=(
                Field("description", "Description", placeholder="Consulting — July"),
                Field("quantity", "Qty", type="number", placeholder="1"),
                Field("rate", "Rate (₹/unit)", type="number", placeholder="10000"),
            )),
        ), _create_invoice),
    ],
    "payables": [
        Action("payables", "create-vendor", "New vendor", (
            Field("name", "Name", placeholder="Sharp Legal LLP"),
            Field("tds_section", "TDS section", type="select", required=False,
                  options=_TDS_SECTIONS),
            Field("payee_type", "Payee type", type="select", options=_PAYEE_TYPES),
            Field("gstin", "GSTIN", required=False, placeholder="29AAAAA0000A1Z5"),
            Field("msme_type", "MSME class", type="select", required=False, options=_MSME_TYPES),
            Field("payment_terms", "Payment terms (days)", type="number", required=False,
                  placeholder="30"),
        ), _create_vendor),
        Action("payables", "create-bill", "Enter bill", (
            Field("bill_number", "Bill number", placeholder="B-1042"),
            Field("vendor_id", "Vendor ID", type="number", placeholder="1"),
            Field("bill_date", "Bill date", type="date"),
            Field("subtotal", "Taxable value (₹)", type="number", placeholder="60000"),
            Field("gst_amount", "GST (₹)", type="number", required=False, placeholder="10800"),
        ), _create_bill),
    ],
    "payroll": [
        Action("payroll", "add-employee", "Add employee", (
            Field("employee_code", "Employee code", placeholder="E001"),
            Field("name", "Name", placeholder="Asha Rao"),
            Field("date_of_joining", "Date of joining", type="date"),
            Field("state", "State (for professional tax)", required=False,
                  placeholder="Karnataka"),
            Field("pan", "PAN", required=False, placeholder="ABCPE1234F"),
        ), _add_employee),
        Action("payroll", "salary-structure", "Set salary structure", (
            Field("employee_id", "Employee ID", type="number", placeholder="1"),
            Field("effective_from", "Effective from", type="date"),
            Field("basic", "Basic (₹/month)", type="number", placeholder="50000"),
            Field("hra", "HRA (₹/month)", type="number", required=False, placeholder="20000"),
            Field("lta", "LTA (₹/month)", type="number", required=False, placeholder="0"),
            Field("special_allowance", "Special allowance (₹/month)", type="number",
                  required=False, placeholder="0"),
        ), _salary_structure),
    ],
    "compliance": [
        Action("compliance", "add-deadline", "Add deadline", (
            Field("domain", "Domain", placeholder="gst"),
            Field("form_name", "Form name", placeholder="GSTR-3B (Jun)"),
            Field("due_date", "Due date", type="date"),
            Field("filing_period", "Filing period", required=False, placeholder="2026-06"),
        ), _add_deadline),
    ],
    "equity": [
        Action("equity", "add-shareholder", "Add shareholder", (
            Field("name", "Name", placeholder="Founder"),
            Field("category", "Category", type="select", options=_SHAREHOLDER_CATS),
            Field("shares_held", "Shares held", type="number", placeholder="700000"),
        ), _add_shareholder),
    ],
    "expense": [
        Action("expense", "submit-claim", "Submit claim", (
            Field("claim_date", "Claim date", type="date"),
            Field("expense_date", "Expense date", type="date"),
            Field("category", "Category", placeholder="travel"),
            Field("amount", "Amount (₹)", type="number", placeholder="5000"),
            # P1-8: receipt OCR (never authoritative) prefills expense_date/amount/vendor_gstin —
            # all three stay editable here, same as every other field.
            Field("vendor_gstin", "Vendor GSTIN", required=False, placeholder="27AAAAA0000A1Z5"),
        ), _submit_claim),
    ],
    "vault": [
        Action("vault", "ingest", "Ingest document", (
            Field("file_name", "File name", placeholder="contract.pdf"),
            Field("content", "Content / OCR text", placeholder="master services agreement…"),
            Field("upload_date", "Upload date", type="date"),
        ), _ingest_document),
    ],
}


def actions_for(domain: str) -> list[Action]:
    return ACTIONS.get(domain, [])


def find_action(domain: str, key: str) -> Action | None:
    return next((a for a in ACTIONS.get(domain, []) if a.key == key), None)
