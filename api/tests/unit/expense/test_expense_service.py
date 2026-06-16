from datetime import date

from app.core.money import Paise
from app.domains.expense.service import ExpenseService


def test_submit_claim_flags_over_policy(session):
    svc = ExpenseService()
    res = svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="meals",
        amount=Paise.from_rupees(3000),  # limit ₹2,000
    )
    assert res["over_policy"] is True
    assert res["excess"] == Paise.from_rupees(1000)
    assert res["petty_cash_eligible"] is True


def test_workflow_states(session):
    svc = ExpenseService()
    res = svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="travel",
        amount=Paise.from_rupees(20000),
    )
    svc.approve_claim(session, res["claim_id"], approver="founder", approved_date="2026-06-11")
    svc.mark_reimbursed(session, res["claim_id"], reimbursement_date="2026-06-12")
    spend = svc.category_spend(session)
    assert spend["travel"] == Paise.from_rupees(20000)


def test_build_snapshot_counts_over_policy(session):
    svc = ExpenseService()
    svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="meals",
        amount=Paise.from_rupees(5000),  # over ₹2,000
    )
    svc.submit_claim(
        session,
        claim_date="2026-06-10",
        expense_date="2026-06-09",
        category="travel",
        amount=Paise.from_rupees(10000),  # within ₹50,000
    )
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["over_policy_claims"] == 1
    assert snap["metrics"]["pending_reimbursement_paise"] == Paise.from_rupees(15000)
