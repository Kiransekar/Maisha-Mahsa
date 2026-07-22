# P0-5: GET /api/treasury/accounts is the ONLY way the re-import picker (Domain.tsx treasury)
# learns a real account id to import into. Called directly as a function (it only takes the
# `db` FastAPI already injects via Depends) rather than through TestClient/JWT — the logic under
# test is serialization, not auth, and RBAC over real HTTP is covered by test_rbac_matrix.py.
#
# Mutation killed: renaming/dropping a field on AccountSummary (e.g. shipping `current_balance`
# instead of `current_balance_paise`, matching Python's attribute name rather than the wire
# contract the SPA's picker actually reads) would fail the exact-value assertions below.

from app.db.models.treasury import BankAccount
from app.domains.treasury.router import list_accounts


def _account(session, bank_name: str, account_number: str, balance_paise: int) -> BankAccount:
    acct = BankAccount(
        bank_name=bank_name,
        account_number=account_number,
        ifsc="HDFC0000001",
        opening_balance=balance_paise,
        current_balance=balance_paise,
    )
    session.add(acct)
    session.flush()
    return acct


def test_no_accounts_is_an_empty_list_not_an_error(session):
    assert list_accounts(db=session) == []


def test_lists_every_account_with_its_real_id_and_balance(session):
    a = _account(session, "HDFC", "0001", 50_000)
    b = _account(session, "ICICI", "0002", 12_345_00)

    result = list_accounts(db=session)

    assert [r.id for r in result] == [a.id, b.id]
    assert [r.bank_name for r in result] == ["HDFC", "ICICI"]
    assert [r.account_number for r in result] == ["0001", "0002"]
    # The re-import target field, exact paise — not the cash_position by-bank-name dict shape.
    assert [r.current_balance_paise for r in result] == [50_000, 12_345_00]
