"""Dev-gated demo-tenant seed (WS11.2 pilot enablement; extends LAUNCH_READINESS P1-FIRSTRUN).

Loads a realistic seed-stage startup so EVERY hub shows real, engine-computed numbers:

* Treasury  — bank statements imported through the REAL ``TreasuryService.import_csv`` path,
  so every transaction carries a citation anchor and the source CSVs live in the Vault
  (SPEC-MEMCITE-1.0 §B3.1: cash-strip figures cite "file, row N" excerpts).
* Ledger    — a Tally day-book XML through the REAL ``parse_tally_xml`` parser, accounts via
  ``LedgerService.create_account``, vouchers via ``post_journal_entry`` with the same
  voucher-hash + source-doc anchors the /api/tally/commit route stamps (§B3.2).
* Payroll   — salary structures via ``PayrollService.set_salary_structure`` (real Labour-Code
  s.2(y) wage-base/PF/ESI/PT computations) and one ``run_payroll`` left in ``draft`` status,
  so the run sits in the approvals queue (PAYROLL-005) — a genuinely pending approval.
* GST       — one GSTR-3B filed late through ``GstService.file_gstr3b`` (late fee + interest
  computed by the real engine; emits the ``interest_3b`` Mahsa recompute claim) and an ITC
  register with a 2B mismatch + an IMS-pending inward invoice.
* Tax       — a pending (unfiled) TDS return via ``TaxService.file_tds_return``.
* Compliance— statutory deadlines via ``ComplianceService.seed_month`` (the service's own
  cited day-of-month table; nothing invented here).
* Expense / Forecast / Equity — claims, a cash projection (net change derived from the real
  treasury metrics, not invented), and the cap table via their services.
* Memory    — CFO posture via ``memory.set_cfo``/``append_cfo``, which SEALS real
  ``memory.update`` events onto the demo org's hash-chained audit log (Audit Room alive).
* History   — two real ``history_store.capture`` runs at different as-of dates so domain
  sparklines have >= 2 genuine points (values computed by the real engines, never drawn).

Statutory values are NEVER invented here (§0.6): every statutory number is produced by the
existing engines/services; the two literal filing dates reused below (GSTR-3B 2026-05 due
2026-06-20; TDS 26Q 2026-Q1 due 2026-07-31) are the exact values already carried by
``tests/unit/gst/test_gst_recompute.py`` and ``tests/unit/tax/test_tax_recompute.py``.

Idempotent — running twice is a no-op. Run with ``make seed`` (``python -m app.dev.seed``).
Refuses to run in production. ``MAISHA_SEED_ORG_ID`` (default ``demo-org``) must match the
Better Auth org id of the demo tenant for the memory/audit-chain rows to render for it.
"""

from __future__ import annotations

import os
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  registers every model on Base.metadata
from app.config import get_settings
from app.core import history_store, memory
from app.core.money import Paise
from app.core.principal import Principal
from app.core.rbac import Role
from app.core.tally_import import parse_tally_xml
from app.db.base import Base
from app.db.models.gst import ItcRegister
from app.db.models.ledger import JournalEntry
from app.domains import build_registry
from app.domains.compliance.service import ComplianceService
from app.domains.expense.service import ExpenseService
from app.domains.forecast.service import ForecastService
from app.domains.gst.service import GstService
from app.domains.ledger.service import LedgerService
from app.domains.payroll.service import PayrollService
from app.domains.tax.service import TaxService
from app.domains.treasury.service import TreasuryService
from app.domains.vault.service import VaultService


def _p(rupees: float) -> int:
    """Rupees -> exact integer paise."""
    return round(rupees * 100)


T = Base.metadata.tables

#: The demo tenant's org id — must match the Better Auth org of the demo login for the
#: memory + per-tenant audit chain to render on its screens.
DEMO_ORG = os.environ.get("MAISHA_SEED_ORG_ID", "demo-org")

_FOUNDER = Principal(
    user_id="founder", org_id=DEMO_ORG, role=Role.OWNER, email="founder@acme-demo.in"
)

# ── Bank statements — imported via the REAL import path (anchors + vault docs) ──────────
# Each month: ₹12L in, ₹20L out → ~₹8L/month net burn.
_BANK_CSV_Q1 = """Date,Description,Debit,Credit,Balance
2026-04-05,Customer receipts,,1200000.00,
2026-04-07,Payroll,1400000.00,,
2026-04-10,Office rent + SaaS,600000.00,,
2026-05-05,Customer receipts,,1200000.00,
2026-05-07,Payroll,1400000.00,,
2026-05-10,Office rent + SaaS,600000.00,,
2026-06-05,Customer receipts,,1200000.00,
2026-06-07,Payroll,1400000.00,,
2026-06-10,Office rent + SaaS,600000.00,,
"""

_BANK_CSV_JUL = """Date,Description,Debit,Credit,Balance
2026-07-05,Customer receipts,,1250000.00,
2026-07-07,Payroll,1400000.00,,
2026-07-10,Office rent + SaaS,600000.00,,
"""

# ── Tally day-book — goes through the REAL parser; same shape as the WS9.1 fixtures ──────
_TALLY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
 <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
 <BODY><IMPORTDATA>
  <REQUESTDESC><REPORTNAME>Day Book</REPORTNAME></REQUESTDESC>
  <REQUESTDATA>
   <TALLYMESSAGE>
    <LEDGER NAME="HDFC Bank" ACTION="Create"><PARENT>Bank Accounts</PARENT></LEDGER>
   </TALLYMESSAGE>
   <TALLYMESSAGE>
    <LEDGER NAME="Sales" ACTION="Create"><PARENT>Sales Accounts</PARENT></LEDGER>
   </TALLYMESSAGE>
   <TALLYMESSAGE>
    <LEDGER NAME="Office Rent" ACTION="Create"><PARENT>Indirect Expenses</PARENT></LEDGER>
   </TALLYMESSAGE>
   <TALLYMESSAGE>
    <LEDGER NAME="Globex Corp" ACTION="Create"><PARENT>Sundry Debtors</PARENT></LEDGER>
   </TALLYMESSAGE>
   <TALLYMESSAGE>
    <VOUCHER VCHTYPE="Sales" ACTION="Create">
     <DATE>20260415</DATE>
     <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
     <VOUCHERNUMBER>1</VOUCHERNUMBER>
     <NARRATION>Invoice INV-2026-001 to Globex Corp</NARRATION>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Globex Corp</LEDGERNAME>
      <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
      <AMOUNT>-800000.00</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Sales</LEDGERNAME>
      <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
      <AMOUNT>800000.00</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
    </VOUCHER>
   </TALLYMESSAGE>
   <TALLYMESSAGE>
    <VOUCHER VCHTYPE="Payment" ACTION="Create">
     <DATE>20260410</DATE>
     <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
     <VOUCHERNUMBER>2</VOUCHERNUMBER>
     <NARRATION>Office rent April</NARRATION>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Office Rent</LEDGERNAME>
      <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
      <AMOUNT>-450000.00</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>HDFC Bank</LEDGERNAME>
      <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
      <AMOUNT>450000.00</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
    </VOUCHER>
   </TALLYMESSAGE>
  </REQUESTDATA>
 </IMPORTDATA></BODY>
</ENVELOPE>
"""

# ledger name -> chart-of-accounts (code, account_type, is_bank); the account_type choices
# mirror app.core.tally_import.TALLY_GROUP_TYPE's group suggestions for these parents.
_TALLY_ACCOUNTS: dict[str, tuple[str, str, bool]] = {
    "HDFC Bank": ("1100", "asset", True),
    "Sales": ("4000", "income", False),
    "Office Rent": ("5100", "expense", False),
    "Globex Corp": ("1300", "asset", False),
}


def already_seeded(db: Session) -> bool:
    return db.execute(select(func.count()).select_from(T["company"])).scalar_one() > 0


def _seed_masters(db: Session) -> None:
    """Company, bank account, customers/invoices, vendors/bills, employees, cap table —
    entered master/book data (not engine outputs), inserted as fixtures."""
    ins = lambda table, **vals: db.execute(T[table].insert().values(**vals))  # noqa: E731

    ins(
        "company",
        id=1,
        name="Acme Innovations Pvt Ltd",
        cin="U72900MH2022PTC123456",
        pan="AAACA1234A",
        gstin="27AAACA1234A1Z5",
        incorporation_date="2022-06-01",
        financial_year_end="03-31",
        sector="SaaS",
        state="MH",
        dpiit_recognition="DIPP12345",
        created_at=datetime(2026, 6, 26),
    )

    # current_balance starts at opening — the CSV imports below move it (real code path).
    ins(
        "bank_accounts",
        id=1,
        bank_name="HDFC Bank",
        account_number="50200012345678",
        ifsc="HDFC0000123",
        account_type="current",
        opening_balance=_p(10_000_000),
        current_balance=_p(10_000_000),
        currency="INR",
        is_primary=1,
    )

    # ── Revenue: 2 customers, 2 invoices (one overdue → AR amber/red) ──
    ins(
        "customers",
        id=1,
        name="Globex Corp",
        gstin="27AABCG1234B1Z9",
        state="MH",
        payment_terms=30,
        tds_applicable=0,
        tds_rate=0.0,
        created_at="2026-01-10",
    )
    ins(
        "customers",
        id=2,
        name="Initech Pvt Ltd",
        gstin="29AABCI5678C1Z3",
        state="KA",
        payment_terms=30,
        tds_applicable=0,
        tds_rate=0.0,
        created_at="2026-02-15",
    )

    # intra-state (MH): CGST+SGST; overdue
    sub1 = _p(800_000)
    g1 = round(sub1 * 0.18)
    ins(
        "invoices",
        id=1,
        invoice_number="INV-2026-001",
        customer_id=1,
        invoice_date="2026-04-15",
        due_date="2026-05-15",
        subtotal=sub1,
        gst_rate=18.0,
        igst_amount=0,
        cgst_amount=g1 // 2,
        sgst_amount=g1 // 2,
        total_amount=sub1 + g1,
        tds_amount=0,
        net_receivable=sub1 + g1,
        status="sent",
        paid_amount=0,
    )
    ins(
        "invoice_items",
        invoice_id=1,
        description="SaaS subscription — Q1",
        hsn_code="998314",
        quantity=1,
        rate=sub1,
        amount=sub1,
    )

    # inter-state (KA): IGST; current
    sub2 = _p(500_000)
    g2 = round(sub2 * 0.18)
    ins(
        "invoices",
        id=2,
        invoice_number="INV-2026-002",
        customer_id=2,
        invoice_date="2026-06-01",
        due_date="2026-07-01",
        subtotal=sub2,
        gst_rate=18.0,
        igst_amount=g2,
        cgst_amount=0,
        sgst_amount=0,
        total_amount=sub2 + g2,
        tds_amount=0,
        net_receivable=sub2 + g2,
        status="sent",
        paid_amount=0,
    )
    ins(
        "invoice_items",
        invoice_id=2,
        description="Implementation services",
        hsn_code="998314",
        quantity=1,
        rate=sub2,
        amount=sub2,
    )

    # ── Payables: 2 vendors (one MSME), 2 bills (MSME bill past its 45-day clock) ──
    ins(
        "vendors",
        id=1,
        name="Micro Supplies Co",
        gstin="27AAACM1111D1Z2",
        msme_status=1,
        msme_type="micro",
        payment_terms=45,
        payee_type="company",
        created_at="2026-01-05",
    )
    ins(
        "vendors",
        id=2,
        name="CloudHost Services",
        gstin="27AAACC2222E1Z4",
        msme_status=0,
        payment_terms=30,
        payee_type="company",
        created_at="2026-01-05",
    )

    bsub1 = _p(300_000)
    bg1 = round(bsub1 * 0.18)
    ins(
        "bills",
        id=1,
        bill_number="BILL-101",
        vendor_id=1,
        bill_date="2026-04-01",
        due_date="2026-05-16",
        subtotal=bsub1,
        gst_amount=bg1,
        igst_amount=0,
        cgst_amount=bg1 // 2,
        sgst_amount=bg1 // 2,
        tds_amount=0,
        total_amount=bsub1 + bg1,
        itc_eligible=1,
        status="approved",
        paid_amount=0,
    )
    bsub2 = _p(150_000)
    bg2 = round(bsub2 * 0.18)
    ins(
        "bills",
        id=2,
        bill_number="BILL-102",
        vendor_id=2,
        bill_date="2026-06-05",
        due_date="2026-07-05",
        subtotal=bsub2,
        gst_amount=bg2,
        igst_amount=bg2,
        cgst_amount=0,
        sgst_amount=0,
        tds_amount=0,
        total_amount=bsub2 + bg2,
        itc_eligible=1,
        status="approved",
        paid_amount=0,
    )

    # ── Employees (master rows; salary structures come from the payroll service) ──
    for eid, code, name in ((1, "EMP001", "Asha Rao"), (2, "EMP002", "Vikram Shah")):
        ins(
            "employees",
            id=eid,
            employee_code=code,
            name=name,
            date_of_joining="2023-07-01",
            status="active",
            state="MH",
            created_at="2023-07-01",
        )

    # ── Equity: founders + ESOP pool + an angel → a real cap table ──
    # ponytail: raw insert (not EquityService.add_shareholder) because the angel's
    # share_premium is a column the service does not accept yet.
    ins(
        "shareholders",
        name="Founder A",
        category="founder",
        investment_amount=_p(100_000),
        shares_held=4_500_000,
        share_premium=0,
        board_seat=1,
    )
    ins(
        "shareholders",
        name="Founder B",
        category="founder",
        investment_amount=_p(100_000),
        shares_held=3_500_000,
        share_premium=0,
        board_seat=1,
    )
    ins(
        "shareholders",
        name="ESOP Pool",
        category="esop",
        investment_amount=0,
        shares_held=1_000_000,
        share_premium=0,
        board_seat=0,
    )
    ins(
        "shareholders",
        name="Seed Angel",
        category="investor",
        investment_amount=_p(2_500_000),
        shares_held=1_000_000,
        share_premium=_p(2_400_000),
        board_seat=0,
    )


def _seed_tally(db: Session) -> int:
    """Parse the demo day-book with the REAL Tally parser and post it through the ledger
    service, stamping the same voucher-hash + source-document anchors the
    ``/api/tally/commit`` route stamps (SPEC-MEMCITE-1.0 §B3.2). Returns vouchers posted."""
    parsed = parse_tally_xml(_TALLY_XML)
    if parsed.errors or parsed.unbalanced:  # pragma: no cover — the fixture is balanced
        raise RuntimeError(f"demo tally file failed the real parser: {parsed.errors}")

    ledger = LedgerService()
    resolution: dict[str, int] = {}
    for name in parsed.ledger_names():
        code, account_type, is_bank = _TALLY_ACCOUNTS[name]
        resolution[name.casefold()] = ledger.create_account(
            db, code=code, name=name, account_type=account_type, is_bank=is_bank
        )

    source_doc = VaultService().ingest_bytes(
        db,
        file_name="acme-daybook-2026-04.xml",
        content=_TALLY_XML,
        upload_date="2026-04-30",
        doc_type="tally_export",
        domain="ledger",
    )
    for v in parsed.vouchers:
        posted = ledger.post_journal_entry(
            db,
            entry_date=v.date or "",
            description=v.narration or v.voucher_type or f"Tally {v.voucher_id}",
            lines=[
                {
                    "account_id": resolution[ln.ledger.casefold()],
                    "debit": ln.debit_paise,
                    "credit": ln.credit_paise,
                }
                for ln in v.lines
            ],
            source="tally",
            reference=v.voucher_id,
        )
        entry = db.get(JournalEntry, posted["journal_entry_id"])
        assert entry is not None  # post_journal_entry just flushed it
        entry.voucher_hash = v.voucher_hash
        entry.source_doc_id = source_doc["id"]
    db.flush()
    return len(parsed.vouchers)


def _seed_gst(db: Session) -> None:
    """GST flows: one GSTR-3B filed 5 days late through the real service (engine-computed
    late fee + interest; emits the ``interest_3b`` recompute claim), plus the ITC register
    behind the two bills — with a 2B gap and an IMS-pending invoice, so the GST detail
    page's reconciliation and IMS queues are alive."""
    # Filing-period/due/filed literals reused verbatim from tests/unit/gst/test_gst_recompute.py
    # (§0.6: no new statutory dates minted here).
    GstService().file_gstr3b(
        db,
        filing_period="2026-05",
        due_date="2026-06-20",
        output={"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
        filed_date="2026-06-25",
    )
    # ITC register rows mirror the BILLS' entered GST amounts (book facts, not statutory
    # computation). ponytail: raw inserts — no service populates the ITC register yet (the
    # 2B feed is a WS9 integration); the reconcile/IMS engines compute over these rows.
    db.add(
        ItcRegister(
            bill_id=1,
            gstin_supplier="27AAACM1111D1Z2",
            invoice_number="BILL-101",
            invoice_date="2026-04-01",
            taxable_value=_p(300_000),
            igst=0,
            cgst=round(_p(300_000) * 0.18) // 2,
            sgst=round(_p(300_000) * 0.18) // 2,
            total_tax=round(_p(300_000) * 0.18),
            eligible_itc=1,
            in_2b=1,
            ims_action="accept",
        )
    )
    db.add(
        ItcRegister(
            bill_id=2,
            gstin_supplier="27AAACC2222E1Z4",
            invoice_number="BILL-102",
            invoice_date="2026-06-05",
            taxable_value=_p(150_000),
            igst=round(_p(150_000) * 0.18),
            cgst=0,
            sgst=0,
            total_tax=round(_p(150_000) * 0.18),
            eligible_itc=1,
            in_2b=0,
            ims_action=None,
        )
    )
    db.flush()


def seed(db: Session) -> dict[str, int]:
    """Load the demo tenant through the real services. Returns row/entity counts.
    No-op if already seeded."""
    if get_settings().environment == "production":
        raise RuntimeError("refusing to seed sample data in production")
    if already_seeded(db):
        return {"skipped": 1}

    _seed_masters(db)

    # ── Treasury: two statements through the REAL import path (anchors + vault docs) ──
    treasury = TreasuryService()
    imp1 = treasury.import_csv(
        db, 1, _BANK_CSV_Q1, file_name="hdfc-50200012345678-apr-jun-2026.csv"
    )
    imp2 = treasury.import_csv(db, 1, _BANK_CSV_JUL, file_name="hdfc-50200012345678-jul-2026.csv")
    bank_rows = imp1["rows_imported"] + imp2["rows_imported"]

    # ── Payroll: structures + June run via the real Labour-Code services ──
    payroll = PayrollService()
    for eid, basic, hra, special in ((1, 60_000, 24_000, 36_000), (2, 45_000, 18_000, 27_000)):
        payroll.set_salary_structure(
            db,
            eid,
            effective_from="2026-04-01",
            basic=_p(basic),
            hra=_p(hra),
            special_allowance=_p(special),
        )
    run = payroll.run_payroll(db, "2026-06", "2026-06-30")
    # The run stays in ``draft`` → PAYROLL-005 folds the domain yellow → it appears in the
    # approvals queue / Exception Inbox as a genuinely pending approval (nothing faked).

    # ── Ledger: Tally day-book through the real parser + posting path ──
    vouchers = _seed_tally(db)

    # ── GST + Tax filings ──
    _seed_gst(db)
    # Pending (unfiled) TDS return; literals reused from tests/unit/tax/test_tax_recompute.py.
    TaxService().file_tds_return(
        db,
        return_type="26Q",
        quarter="2026-Q1",
        due_date="2026-07-31",
        total_deducted=Paise.from_rupees(50000),
    )

    # ── Compliance calendar: the service's own statutory day-of-month table ──
    compliance = ComplianceService()
    deadlines = sum(len(compliance.seed_month(db, month)) for month in ("2026-06", "2026-07"))

    # ── Expense: two claims (one over-policy), one approved ──
    expense = ExpenseService()
    claim = expense.submit_claim(
        db,
        claim_date="2026-07-01",
        expense_date="2026-06-28",
        category="travel",
        amount=_p(18_500),
        gst_amount=_p(2_822),
        employee_id=1,
        vendor_name="MakeMyTrip",
        description="Customer visit — Bengaluru",
    )
    expense.approve_claim(db, claim["claim_id"], approver="founder", approved_date="2026-07-02")
    expense.submit_claim(
        db,
        claim_date="2026-07-10",
        expense_date="2026-07-09",
        category="meals",
        amount=_p(4_800),
        employee_id=2,
        vendor_name="Cafe Aroma",
        description="Team dinner (over policy — needs review)",
    )

    # ── Forecast: projection from the REAL treasury metrics (nothing invented) ──
    m = treasury.metrics(db, date(2026, 7, 15))
    ForecastService().record_forecast(
        db,
        forecast_date="2026-07-15",
        opening_cash=m["cash_paise"],
        monthly_net_change=[-m["net_burn_paise"]] * 12,
    )

    # ── Memory + audit chain: CFO posture sealed as real memory.update events ──
    memory.set_cfo(
        db,
        _FOUNDER,
        "Seed-stage SaaS, Maharashtra. Priorities: extend runway past 12 months, "
        "close the Globex overdue invoice, keep GST/TDS filings on time.",
        now="2026-07-01T09:00:00+05:30",
    )
    memory.append_cfo(
        db,
        _FOUNDER,
        "Decision: pay MSME vendors within the 45-day clock even under cash pressure.",
        now="2026-07-10T09:00:00+05:30",
    )

    # ── History: two REAL captures at different as-of dates → honest sparklines ──
    registry = build_registry()
    history_store.capture(db, registry, captured_at="2026-06-30", as_of=date(2026, 6, 30))
    history_store.capture(db, registry, captured_at="2026-07-15", as_of=date(2026, 7, 15))

    db.commit()
    return {
        "company": 1,
        "bank_accounts": 1,
        "bank_transactions": bank_rows,
        "vault_documents": 3,
        "customers": 2,
        "invoices": 2,
        "vendors": 2,
        "bills": 2,
        "employees": run["employee_count"],
        "payroll_runs": 1,
        "journal_vouchers": vouchers,
        "gst_returns": 1,
        "itc_rows": 2,
        "tds_returns": 1,
        "deadlines": deadlines,
        "expense_claims": 2,
        "forecasts": 1,
        "shareholders": 4,
        "memory_events": 2,
    }


def main() -> None:
    from app.db.session import make_engine, make_session_factory

    engine = make_engine()
    Base.metadata.create_all(engine)  # dev convenience; seed is dev-gated
    db = make_session_factory(engine)()
    try:
        result = seed(db)
        if result.get("skipped"):
            print("Already seeded — no changes.")
        else:
            total = sum(result.values())
            print(
                f"Seeded demo tenant 'Acme Innovations' for org '{DEMO_ORG}' "
                f"({total} entities): " + ", ".join(f"{k}={v}" for k, v in result.items())
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
