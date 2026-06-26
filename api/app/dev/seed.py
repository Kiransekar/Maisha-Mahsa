"""Dev-gated sample-company seed (LAUNCH_READINESS P1-FIRSTRUN).

Loads a realistic seed-stage startup so every screen shows real numbers instead of ₹0.00:
cash + burn + runway, AR (with an overdue invoice), AP (with an MSME-clock breach), two
employees with salary structures, and a cap table. Idempotent — running twice is a no-op.

Run with ``make seed`` (or ``python -m app.dev.seed``). Refuses to run in production.
ponytail: inserts straight through SQLAlchemy Core into the model tables; amounts are exact
integer paise, dates are fixed literals (a dev fixture needs no clock).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  registers every model on Base.metadata
from app.config import get_settings
from app.db.base import Base


def _p(rupees: float) -> int:
    """Rupees -> exact integer paise."""
    return round(rupees * 100)


T = Base.metadata.tables


def already_seeded(db: Session) -> bool:
    return db.execute(select(func.count()).select_from(T["company"])).scalar_one() > 0


def seed(db: Session) -> dict[str, int]:
    """Insert the sample company. Returns row counts. No-op if already seeded."""
    if get_settings().environment == "production":
        raise RuntimeError("refusing to seed sample data in production")
    if already_seeded(db):
        return {"skipped": 1}

    ins = lambda table, **vals: db.execute(T[table].insert().values(**vals))  # noqa: E731

    ins(
        "company",
        id=1, name="Acme Innovations Pvt Ltd", cin="U72900MH2022PTC123456",
        pan="AAACA1234A", gstin="27AAACA1234A1Z5", incorporation_date="2022-06-01",
        financial_year_end="03-31", sector="SaaS", state="MH",
        dpiit_recognition="DIPP12345", created_at=datetime(2026, 6, 26),
    )

    # ── Treasury: one bank account + 3 months of txns → positive cash, real burn ──
    ins(
        "bank_accounts",
        id=1, bank_name="HDFC Bank", account_number="50200012345678", ifsc="HDFC0000123",
        account_type="current", opening_balance=_p(10_000_000), current_balance=_p(8_500_000),
        currency="INR", is_primary=1,
    )
    # each month: ₹12L in, ₹20L out → ~₹8L/month net burn
    for month, day in (("2026-04", "05"), ("2026-05", "05"), ("2026-06", "05")):
        ins("bank_transactions", account_id=1, txn_date=f"{month}-{day}",
            description="Customer receipts", credit=_p(1_200_000), debit=0,
            category="revenue", is_reconciled=1)
        ins("bank_transactions", account_id=1, txn_date=f"{month}-07",
            description="Payroll", credit=0, debit=_p(1_400_000),
            category="payroll", is_reconciled=1)
        ins("bank_transactions", account_id=1, txn_date=f"{month}-10",
            description="Office rent + SaaS", credit=0, debit=_p(600_000),
            category="opex", is_reconciled=0)

    # ── Revenue: 2 customers, 2 invoices (one overdue → AR amber/red) ──
    ins("customers", id=1, name="Globex Corp", gstin="27AABCG1234B1Z9", state="MH",
        payment_terms=30, tds_applicable=0, tds_rate=0.0, created_at="2026-01-10")
    ins("customers", id=2, name="Initech Pvt Ltd", gstin="29AABCI5678C1Z3", state="KA",
        payment_terms=30, tds_applicable=0, tds_rate=0.0, created_at="2026-02-15")

    # intra-state (MH): CGST+SGST; overdue
    sub1 = _p(800_000)
    g1 = round(sub1 * 0.18)
    ins("invoices", id=1, invoice_number="INV-2026-001", customer_id=1,
        invoice_date="2026-04-15", due_date="2026-05-15", subtotal=sub1, gst_rate=18.0,
        igst_amount=0, cgst_amount=g1 // 2, sgst_amount=g1 // 2, total_amount=sub1 + g1,
        tds_amount=0, net_receivable=sub1 + g1, status="sent", paid_amount=0)
    ins("invoice_items", invoice_id=1, description="SaaS subscription — Q1",
        hsn_code="998314", quantity=1, rate=sub1, amount=sub1)

    # inter-state (KA): IGST; current
    sub2 = _p(500_000)
    g2 = round(sub2 * 0.18)
    ins("invoices", id=2, invoice_number="INV-2026-002", customer_id=2,
        invoice_date="2026-06-01", due_date="2026-07-01", subtotal=sub2, gst_rate=18.0,
        igst_amount=g2, cgst_amount=0, sgst_amount=0, total_amount=sub2 + g2,
        tds_amount=0, net_receivable=sub2 + g2, status="sent", paid_amount=0)
    ins("invoice_items", invoice_id=2, description="Implementation services",
        hsn_code="998314", quantity=1, rate=sub2, amount=sub2)

    # ── Payables: 2 vendors (one MSME), 2 bills (MSME bill past its 45-day clock) ──
    ins("vendors", id=1, name="Micro Supplies Co", gstin="27AAACM1111D1Z2", msme_status=1,
        msme_type="micro", payment_terms=45, payee_type="company", created_at="2026-01-05")
    ins("vendors", id=2, name="CloudHost Services", gstin="27AAACC2222E1Z4", msme_status=0,
        payment_terms=30, payee_type="company", created_at="2026-01-05")

    bsub1 = _p(300_000)
    bg1 = round(bsub1 * 0.18)
    ins("bills", id=1, bill_number="BILL-101", vendor_id=1, bill_date="2026-04-01",
        due_date="2026-05-16", subtotal=bsub1, gst_amount=bg1, igst_amount=0,
        cgst_amount=bg1 // 2, sgst_amount=bg1 // 2, tds_amount=0, total_amount=bsub1 + bg1,
        itc_eligible=1, status="approved", paid_amount=0)
    bsub2 = _p(150_000)
    bg2 = round(bsub2 * 0.18)
    ins("bills", id=2, bill_number="BILL-102", vendor_id=2, bill_date="2026-06-05",
        due_date="2026-07-05", subtotal=bsub2, gst_amount=bg2, igst_amount=bg2,
        cgst_amount=0, sgst_amount=0, tds_amount=0, total_amount=bsub2 + bg2,
        itc_eligible=1, status="approved", paid_amount=0)

    # ── Payroll: 2 employees + salary structures ──
    for eid, code, name, basic, hra, special in (
        (1, "EMP001", "Asha Rao", 6_00_000, 2_40_000, 3_60_000),
        (2, "EMP002", "Vikram Shah", 4_50_000, 1_80_000, 2_70_000),
    ):
        ins("employees", id=eid, employee_code=code, name=name,
            date_of_joining="2023-07-01", status="active", state="MH",
            created_at="2023-07-01")
        gross = basic + hra + special
        # PF on the ₹15k statutory ceiling; the monthly payroll run recomputes all statutory.
        pf = round(min(basic, 15_000) * 0.12)
        ins("salary_structures", employee_id=eid, effective_from="2026-04-01",
            basic=_p(basic), hra=_p(hra), lta=0, special_allowance=_p(special),
            employer_pf=_p(pf), employer_esi=0, employee_pf=_p(pf), employee_esi=0,
            professional_tax=_p(200), tds_monthly=0,
            gross_salary=_p(gross), net_salary=_p(gross), ctc=_p(gross * 12))

    # ── Equity: founders + ESOP pool + an angel → a real cap table ──
    ins("shareholders", name="Founder A", category="founder", investment_amount=_p(100_000),
        shares_held=4_500_000, share_premium=0, board_seat=1)
    ins("shareholders", name="Founder B", category="founder", investment_amount=_p(100_000),
        shares_held=3_500_000, share_premium=0, board_seat=1)
    ins("shareholders", name="ESOP Pool", category="esop", investment_amount=0,
        shares_held=1_000_000, share_premium=0, board_seat=0)
    ins("shareholders", name="Seed Angel", category="investor", investment_amount=_p(2_500_000),
        shares_held=1_000_000, share_premium=_p(2_400_000), board_seat=0)

    db.commit()
    return {
        "company": 1, "bank_accounts": 1, "bank_transactions": 9, "customers": 2,
        "invoices": 2, "vendors": 2, "bills": 2, "employees": 2, "shareholders": 4,
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
            print(f"Seeded sample company '{result.get('company') and 'Acme Innovations'}' "
                  f"({total} rows): " + ", ".join(f"{k}={v}" for k, v in result.items()))
    finally:
        db.close()


if __name__ == "__main__":
    main()
