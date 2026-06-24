"""Double-entry accounting core — pure, exact (integer paise), deterministic.

Implements the balance check, trial balance, P&L, balance sheet and depreciation
(SLM / WDV, Companies Act Schedule II). Normal balances: asset/expense are debit-natured;
liability/equity/income are credit-natured.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEBIT_NATURED = ("asset", "expense")
CREDIT_NATURED = ("liability", "equity", "income")


def _round_rupee(paise: Decimal) -> int:
    return int((paise / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100


def is_balanced(lines: list[dict]) -> bool:
    """A journal entry is valid only when total debits equal total credits."""
    return sum(int(ln.get("debit", 0)) for ln in lines) == sum(
        int(ln.get("credit", 0)) for ln in lines
    )


def trial_balance(lines: list[dict]) -> dict[str, Any]:
    """Totals across all posted lines. ``diff`` must be 0 for the books to tie out."""
    total_debit = sum(int(ln.get("debit", 0)) for ln in lines)
    total_credit = sum(int(ln.get("credit", 0)) for ln in lines)
    return {
        "total_debit": total_debit,
        "total_credit": total_credit,
        "diff": total_debit - total_credit,
        "balanced": total_debit == total_credit,
    }


def _net_by_nature(rows: list[dict], account_type: str) -> int:
    """Net movement for an account type. Debit-natured types return debit−credit;
    credit-natured return credit−debit."""
    total = 0
    for r in rows:
        if r["account_type"] != account_type:
            continue
        debit, credit = int(r.get("debit", 0)), int(r.get("credit", 0))
        total += (debit - credit) if account_type in DEBIT_NATURED else (credit - debit)
    return total


def profit_and_loss(rows: list[dict]) -> dict[str, int]:
    """rows: {account_type, debit, credit}. Returns income, expense, net_profit (paise)."""
    income = _net_by_nature(rows, "income")
    expense = _net_by_nature(rows, "expense")
    return {"income": income, "expense": expense, "net_profit": income - expense}


def balance_sheet(rows: list[dict]) -> dict[str, Any]:
    """Assets vs liabilities + equity + retained profit. ``balanced`` ⇔ the accounting
    equation holds."""
    assets = _net_by_nature(rows, "asset")
    liabilities = _net_by_nature(rows, "liability")
    equity = _net_by_nature(rows, "equity")
    net_profit = profit_and_loss(rows)["net_profit"]
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "retained_profit": net_profit,
        "balanced": assets == liabilities + equity + net_profit,
    }


def slm_annual(cost: int, salvage: int, useful_life_years: int) -> int:
    """Straight-line depreciation per year = (cost − salvage) / life."""
    if useful_life_years <= 0:
        return 0
    return _round_rupee(Decimal(int(cost) - int(salvage)) / useful_life_years)


def wdv_annual(opening_wdv: int, rate_pct: float) -> int:
    """Written-down-value depreciation for one year = opening WDV × rate."""
    return _round_rupee(Decimal(int(opening_wdv)) * Decimal(str(rate_pct)) / 100)


def bank_reconciliation(
    book_balance: int,
    bank_statement_balance: int,
    *,
    deposits_in_transit: int = 0,
    unpresented_cheques: int = 0,
) -> dict[str, Any]:
    """Reconcile the cash-book balance to the bank statement. Adjusted bank balance =
    statement + deposits in transit − unpresented cheques; reconciled when it ties to the
    book balance (exact paise)."""
    adjusted = int(bank_statement_balance) + int(deposits_in_transit) - int(unpresented_cheques)
    difference = int(book_balance) - adjusted
    return {
        "book_balance": int(book_balance),
        "adjusted_bank_balance": adjusted,
        "difference": difference,
        "reconciled": difference == 0,
    }
