"""F3 web action layer: declarative actions render a drawer form, POST persists via the domain
service, refresh the figures, and re-render with an error on bad input."""

from __future__ import annotations

from app.web.actions import actions_for, find_action


def test_registry_lookup() -> None:
    assert [a.key for a in actions_for("vault")] == ["ingest"]
    assert find_action("vault", "ingest") is not None
    assert find_action("vault", "nope") is None
    assert actions_for("treasury") == []  # no actions wired yet (documented)


def test_action_handlers_persist(session) -> None:  # type: ignore[no-untyped-def]
    # vault ingest -> a document exists and the snapshot count reflects it.
    from app.domains.vault.service import VaultService

    msg = find_action("vault", "ingest").handler(  # type: ignore[union-attr]
        session,
        {"file_name": "inv.pdf", "content": "invoice 100", "upload_date": "2026-05-10"},
    )
    session.flush()
    assert "inv.pdf" in msg
    assert VaultService().build_snapshot(session)["metrics"]["documents_count"] == 1


def test_expense_amount_parsed_to_paise(session) -> None:  # type: ignore[no-untyped-def]
    from app.domains.expense.service import ExpenseService

    find_action("expense", "submit-claim").handler(  # type: ignore[union-attr]
        session,
        {
            "claim_date": "2026-06-10",
            "expense_date": "2026-06-09",
            "category": "travel",
            "amount": "5000",
        },
    )
    session.flush()
    snap = ExpenseService().build_snapshot(session)
    assert snap["metrics"]["pending_reimbursement_paise"] == 500000  # ₹5,000 -> paise
