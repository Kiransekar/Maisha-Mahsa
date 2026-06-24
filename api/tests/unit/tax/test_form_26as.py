"""Form 26AS reconciliation — deferred feature."""

from __future__ import annotations

from app.domains.tax.tax_calc import reconcile_26as


def test_clean_match_reconciles() -> None:
    res = reconcile_26as(
        [{"tan": "AAAA11111A", "amount": 5000}],
        [{"tan": "AAAA11111A", "amount": 5000}],
    )
    assert res["reconciled"] is True
    assert res["matched"] == [{"tan": "AAAA11111A", "amount": 5000}]


def test_flags_one_sided_and_mismatched() -> None:
    res = reconcile_26as(
        books=[{"tan": "AAAA", "amount": 5000}, {"tan": "BBBB", "amount": 3000},
               {"tan": "DDDD", "amount": 1000}],
        as_26as=[{"tan": "AAAA", "amount": 5000}, {"tan": "BBBB", "amount": 2500},
                 {"tan": "CCCC", "amount": 900}],
    )
    assert res["reconciled"] is False
    assert {"tan": "AAAA", "amount": 5000} in res["matched"]
    assert res["mismatched"][0]["tan"] == "BBBB" and res["mismatched"][0]["variance"] == 500
    assert res["missing_in_26as"] == [{"tan": "DDDD", "books": 1000}]   # in books, not dept
    assert res["missing_in_books"] == [{"tan": "CCCC", "as_26as": 900}]  # in dept, not books
