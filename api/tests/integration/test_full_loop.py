"""The real end-to-end loop: treasury snapshot → real Mahsa binary over HTTP →
fold/validate/unfold → sealed into the hash-chained audit log. This is the bottom-up
proof that the whole stack works together."""

from datetime import date

import pytest

from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.cfo import collect_health, compose_brief
from app.core.email.channel import EmailChannel
from app.core.email.transport import InMemoryTransport
from app.core.loop import run_loop
from app.core.mahsa_client import MahsaClient
from app.core.money import Paise
from app.db.models.gst import GstReturn
from app.db.models.payables import Vendor
from app.db.models.payroll import Employee
from app.db.models.revenue import Customer
from app.db.models.tax import TdsEntry
from app.db.models.treasury import BankAccount, BankTransaction
from app.domains import build_registry
from app.domains.compliance.service import ComplianceService
from app.domains.equity.service import EquityService
from app.domains.expense.service import ExpenseService
from app.domains.forecast.service import ForecastService
from app.domains.gst.service import GstService
from app.domains.ledger.service import LedgerService
from app.domains.payables.service import PayablesService
from app.domains.payroll.service import PayrollService
from app.domains.revenue.service import RevenueService
from app.domains.tax.service import TaxService
from app.domains.treasury.service import TreasuryService
from app.domains.vault.service import VaultService

pytestmark = pytest.mark.integration


async def test_distressed_treasury_loop_is_red_and_audited(session, mahsa_server):
    # ₹3,00,000 cash, ₹9,00,000 burned over 3 months -> 1-month runway -> RED.
    acct = BankAccount(
        bank_name="HDFC",
        account_number="1",
        ifsc="HDFC0000001",
        current_balance=Paise.from_rupees(300000),
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-05-10",
            debit=Paise.from_rupees(900000),
            credit=0,
        )
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=TreasuryService(),
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="treasury.fold",
    )

    assert outcome.fold.validation.status == "red"
    assert any(t.id == "TREASURY-001" for t in outcome.fold.validation.triggered)
    assert outcome.fold.shape.requires_approval is True
    assert outcome.fold.domain == "treasury"
    assert len(outcome.fold.global_intent) == 8

    chain = load_chain(session)
    assert len(chain) == 1
    assert chain[0].validation_status == "red"
    assert verify_chain(chain) is True


async def test_healthy_treasury_loop_is_green(session, mahsa_server):
    acct = BankAccount(
        bank_name="HDFC",
        account_number="1",
        ifsc="HDFC0000001",
        current_balance=Paise.from_rupees(12000000),  # ₹1.2 Cr
    )
    session.add(acct)
    session.flush()
    session.add(
        BankTransaction(
            account_id=acct.id,
            txn_date="2026-06-01",
            debit=Paise.from_rupees(300000),
            credit=Paise.from_rupees(600000),
        )
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=TreasuryService(),
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
    )
    assert outcome.fold.validation.status == "green"
    assert outcome.fold.shape.requires_approval is False


async def test_payroll_loop_folds_and_audits(session, mahsa_server):
    svc = PayrollService()
    emp = Employee(employee_code="E1", name="Asha", date_of_joining="2021-04-01", state="MH")
    session.add(emp)
    session.flush()
    svc.set_salary_structure(
        session,
        emp.id,
        effective_from="2026-04-01",
        basic=Paise.from_rupees(50000),
        hra=Paise.from_rupees(20000),
        special_allowance=Paise.from_rupees(30000),
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="payroll.fold",
    )
    # healthy payroll (correct statutory math, positive net) -> green, 8-dim payroll vector
    assert outcome.fold.domain == "payroll"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.fold.validation.status == "green"
    assert outcome.snapshot["metrics"]["min_net_pay_paise"] == Paise.from_rupees(98000)
    # Prime Directive: run_loop sent payroll's recompute claims and Mahsa verified every one to
    # the paisa (a mismatch would have forced a MAHSA-PARITY-001 block, i.e. red).
    assert outcome.fold.recompute, "payroll should emit recompute claims"
    assert all(c.matches for c in outcome.fold.recompute)
    assert not any(t.id == "MAHSA-PARITY-001" for t in outcome.fold.validation.triggered)

    chain = load_chain(session)
    assert verify_chain(chain) is True


async def test_payroll_recompute_mismatch_blocks_live(session, mahsa_server):
    # A tampered payroll figure must be BLOCKED by Mahsa's independent recomputation (§0.4).
    svc = PayrollService()
    emp = Employee(employee_code="E9", name="Ravi", date_of_joining="2021-04-01", state="MH")
    session.add(emp)
    session.flush()
    # Basic ₹18k (< ₹21k ESI ceiling) so PF and ESI both fire -> richer claim set.
    svc.set_salary_structure(
        session, emp.id, effective_from="2026-04-01", basic=Paise.from_rupees(18000), hra=0
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    snapshot = svc.build_snapshot(session, date(2026, 6, 16))
    claims = svc.recompute_claims(session, date(2026, 6, 16))
    assert claims

    # Correct claims verify and do not block.
    ok = await mahsa.fold(snapshot, domain="payroll", recompute_claims=claims)
    assert all(c.matches for c in ok.recompute)
    assert not any(t.id == "MAHSA-PARITY-001" for t in ok.validation.triggered)

    # Tamper one claimed figure by ₹1 -> Mahsa recomputes the true value and BLOCKS.
    tampered = list(claims)
    i = next(k for k, c in enumerate(tampered) if c.target == "pf_employee")
    tampered[i] = tampered[i].model_copy(update={"claimed_paise": tampered[i].claimed_paise + 100})
    blocked = await mahsa.fold(snapshot, domain="payroll", recompute_claims=tampered)
    assert blocked.validation.status == "red"
    assert any(t.id == "MAHSA-PARITY-001" for t in blocked.validation.triggered)
    assert any(not c.matches and c.recomputed_paise is not None for c in blocked.recompute)


async def test_gst_overdue_filing_loop_is_red_and_audited(session, mahsa_server):
    svc = GstService()
    # GSTR-3B for Apr 2026 unfiled, due 20 May -> overdue at as_of 16 Jun -> GST-001 block
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-04",
            due_date="2026-05-20",
            status="pending",
        )
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="gst.fold",
    )
    assert outcome.fold.domain == "gst"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.fold.validation.status == "red"
    assert any(t.id == "GST-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_revenue_missing_einvoice_loop_is_red(session, mahsa_server):
    rev = RevenueService()
    cust = Customer(name="BigCo", state="MH", payment_terms=30)
    session.add(cust)
    session.flush()
    # ₹6 Cr invoice without an IRN -> turnover > ₹5 Cr + missing e-invoice -> REVENUE-001
    rev.create_invoice(
        session,
        invoice_number="INV-BIG",
        customer_id=cust.id,
        invoice_date="2026-05-10",
        lines=[{"description": "Platform", "quantity": 1, "rate": Paise.from_rupees(60000000)}],
        gst_rate=18,
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=rev,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="revenue.fold",
    )
    assert outcome.fold.domain == "revenue"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.fold.validation.status == "red"
    assert any(t.id == "REVENUE-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_payables_msme_overdue_loop_is_yellow(session, mahsa_server):
    pay = PayablesService()
    vendor = Vendor(name="MSME Co", msme_status=1, payment_terms=30)
    session.add(vendor)
    session.flush()
    # bill dated 1 Apr, unpaid at 16 Jun -> 76 days > 45 -> PAYABLES-001 warning
    pay.create_bill(
        session,
        bill_number="B-MSME",
        vendor_id=vendor.id,
        bill_date="2026-04-01",
        subtotal=Paise.from_rupees(50000),
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=pay,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="payables.fold",
    )
    assert outcome.fold.domain == "payables"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.fold.validation.status == "yellow"
    assert any(t.id == "PAYABLES-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_tax_overdue_tds_deposit_loop_is_red(session, mahsa_server):
    svc = TaxService()
    # TDS deducted 10 Apr -> due 7 May -> unpaid at 16 Jun -> TAX-002 block
    session.add(
        TdsEntry(
            deductee_name="X",
            section="194J",
            payment_date="2026-04-10",
            payment_amount=Paise.from_rupees(50000),
            tds_amount=Paise.from_rupees(5000),
            total_tds=Paise.from_rupees(5000),
        )
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="tax.fold",
    )
    assert outcome.fold.domain == "tax"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.fold.validation.status == "red"
    assert any(t.id == "TAX-002" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_ledger_balanced_books_loop_is_green(session, mahsa_server):
    svc = LedgerService()
    cash = svc.create_account(session, code="1000", name="Cash", account_type="asset")
    capital = svc.create_account(session, code="3000", name="Capital", account_type="equity")
    svc.post_journal_entry(
        session,
        entry_date="2026-05-01",
        description="capital introduced",
        lines=[
            {"account_id": cash, "debit": Paise.from_rupees(100000), "credit": 0},
            {"account_id": capital, "debit": 0, "credit": Paise.from_rupees(100000)},
        ],
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="ledger.fold",
    )
    # ledger has no sub-vector; balanced books -> LEDGER-001 silent -> green
    assert outcome.fold.domain is None
    assert outcome.fold.domain_intent is None
    assert outcome.snapshot["metrics"]["trial_balance_diff_paise"] == 0
    assert outcome.fold.validation.status == "green"
    assert verify_chain(load_chain(session)) is True


async def test_compliance_overdue_filing_loop_is_yellow(session, mahsa_server):
    svc = ComplianceService()
    # GSTR-3B for Apr due 20 May, unfiled at 16 Jun -> overdue -> global COMPLIANCE-002
    svc.add_deadline(
        session,
        domain="gst",
        form_name="GSTR-3B (Apr)",
        due_date="2026-05-20",
        filing_period="2026-04",
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="compliance.fold",
    )
    assert outcome.fold.domain == "compliance"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.snapshot["overdue_filings"] == 1
    assert outcome.fold.validation.status == "yellow"
    assert any(t.id == "COMPLIANCE-002" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_equity_esop_over_cap_loop_is_red(session, mahsa_server):
    svc = EquityService()
    svc.add_shareholder(session, name="Founder", category="founder", shares_held=700000)
    svc.add_shareholder(session, name="VC", category="investor", shares_held=170000)
    svc.add_shareholder(session, name="ESOP", category="esop", shares_held=130000)  # 13%
    svc.snapshot_cap_table(session, snapshot_date="2026-06-01", esop_board_approved=False)
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="equity.fold",
    )
    assert outcome.fold.domain == "equity"
    assert len(outcome.fold.domain_intent) == 8
    assert outcome.snapshot["metrics"]["esop_pool_pct"] == 0.13
    assert outcome.fold.validation.status == "red"
    assert any(t.id == "EQUITY-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_forecast_projected_overdraft_loop_is_yellow(session, mahsa_server):
    svc = ForecastService()
    # ₹3L cash burning ₹1L/mo for 4 months -> projected cash goes negative -> FORECAST-001
    svc.record_forecast(
        session,
        forecast_date="2026-06-16",
        opening_cash=Paise.from_rupees(300000),
        monthly_net_change=[Paise.from_rupees(-100000)] * 4,
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="forecast.fold",
    )
    # forecast has no sub-vector; projected overdraft -> FORECAST-001 warning
    assert outcome.fold.domain is None
    assert outcome.fold.domain_intent is None
    assert outcome.snapshot["metrics"]["forecast_min_cash_paise"] < 0
    assert outcome.fold.validation.status == "yellow"
    assert any(t.id == "FORECAST-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_expense_over_policy_loop_is_yellow(session, mahsa_server):
    svc = ExpenseService()
    # ₹5,000 meals claim against a ₹2,000 limit -> over policy -> EXPENSE-001
    svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="meals",
        amount=Paise.from_rupees(5000),
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="expense.fold",
    )
    assert outcome.fold.domain is None  # no sub-vector
    assert outcome.snapshot["metrics"]["over_policy_claims"] == 1
    assert outcome.fold.validation.status == "yellow"
    assert any(t.id == "EXPENSE-001" for t in outcome.fold.validation.triggered)
    assert verify_chain(load_chain(session)) is True


async def test_vault_healthy_ingest_loop_is_green(session, mahsa_server):
    svc = VaultService()
    svc.ingest(
        session,
        file_name="May_invoice.pdf",
        content="invoice total 600",
        upload_date="2026-05-10",
        domain="revenue",
    )
    session.commit()

    mahsa = MahsaClient(mahsa_server)
    outcome = await run_loop(
        session=session,
        mahsa=mahsa,
        service=svc,
        timestamp="2026-06-16T20:00:00+00:00",
        as_of=date(2026, 6, 16),
        action="vault.fold",
    )
    # vault has no sub-vector; intact documents -> VAULT-001 silent -> green
    assert outcome.fold.domain is None
    assert outcome.snapshot["metrics"]["documents_count"] == 1
    assert outcome.snapshot["metrics"]["integrity_failures"] == 0
    assert outcome.fold.validation.status == "green"
    assert verify_chain(load_chain(session)) is True


async def test_cfo_brief_folds_all_domains_and_emails(session, mahsa_server):
    """Layer 5: the daily CFO brief collects every domain's health through the real Mahsa
    and dispatches via the email channel (in-memory transport)."""
    mahsa = MahsaClient(mahsa_server)
    health = await collect_health(session, mahsa, build_registry(), as_of=date(2026, 6, 16))
    assert len(health) == 12  # all domains folded
    # empty books -> nothing in breach -> everything green
    assert all(h.status == "green" for h in health)

    brief = compose_brief("2026-06-16", health)
    assert brief.needs_attention == []
    assert brief.overall_score is not None

    transport = InMemoryTransport()
    html = await EmailChannel(transport).send_daily_brief(to="founder@x.test", brief=brief)
    assert len(transport.sent) == 1
    assert "all green" in transport.sent[0].subject
    assert "Domain Health" in html
