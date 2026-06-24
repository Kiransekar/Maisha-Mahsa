"""Account-wise general ledger view — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.ledger.service import LedgerService


def _books(session):  # type: ignore[no-untyped-def]
    svc = LedgerService()
    ids = {
        "cash": svc.create_account(session, code="1000", name="Cash", account_type="asset"),
        "capital": svc.create_account(session, code="3000", name="Capital", account_type="equity"),
        "sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
        "rent": svc.create_account(session, code="5000", name="Rent", account_type="expense"),
    }

    def je(desc, dr, cr, amt):  # type: ignore[no-untyped-def]
        svc.post_journal_entry(
            session, entry_date="2026-05-01", description=desc,
            lines=[
                {"account_id": ids[dr], "debit": Paise.from_rupees(amt), "credit": 0},
                {"account_id": ids[cr], "debit": 0, "credit": Paise.from_rupees(amt)},
            ],
        )

    je("capital", "cash", "capital", 3000)
    je("sale", "cash", "sales", 4000)
    je("rent", "rent", "cash", 1000)
    return svc, ids


def test_general_ledger_running_balance(session) -> None:  # type: ignore[no-untyped-def]
    svc, ids = _books(session)
    gl = svc.general_ledger(session, ids["cash"])
    assert gl["code"] == "1000"
    assert len(gl["lines"]) == 3
    # cash: +3,000 +4,000 −1,000 = 6,000
    assert gl["lines"][-1]["balance"] == Paise.from_rupees(6000)
    assert gl["closing_balance"] == Paise.from_rupees(6000)


def test_unknown_account_raises(session) -> None:  # type: ignore[no-untyped-def]
    try:
        LedgerService().general_ledger(session, 9999)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
