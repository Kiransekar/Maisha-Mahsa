"""Ledger service: chart of accounts, balanced journal posting, financial statements,
depreciation, and the ledger health snapshot for Mahsa. Exact paise; deterministic.

Ledger has no Mahsa sub-vector (it is not one of the 8 health domains); instead Mahsa
enforces LEDGER-001 (trial balance must tie out) on the snapshot's ``trial_balance_diff``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.ledger import ChartOfAccounts, FixedAsset, JournalEntry, JournalLine
from app.domains.ledger import ledger_calc
from app.domains.ledger.manifest import MANIFEST


class LedgerService(BaseDomainService):
    domain = "ledger"
    keywords = (
        "journal",
        "ledger",
        "trial balance",
        "p&l",
        "pnl",
        "balance sheet",
        "depreciation",
        "account",
        "books",
    )
    manifest = MANIFEST

    # ---- chart of accounts ----------------------------------------------------------

    def create_account(
        self,
        session: Session,
        *,
        code: str,
        name: str,
        account_type: str,
        sub_type: str | None = None,
        opening_balance: int = 0,
    ) -> int:
        if account_type not in (*ledger_calc.DEBIT_NATURED, *ledger_calc.CREDIT_NATURED):
            raise ValueError(f"invalid account_type: {account_type}")
        acct = ChartOfAccounts(
            code=code,
            name=name,
            account_type=account_type,
            sub_type=sub_type,
            opening_balance=opening_balance,
        )
        session.add(acct)
        session.flush()
        return acct.id

    # ---- journal --------------------------------------------------------------------

    def post_journal_entry(
        self,
        session: Session,
        *,
        entry_date: str,
        description: str,
        lines: list[dict],
        source: str = "manual",
        reference: str | None = None,
    ) -> dict[str, Any]:
        """Post a balanced journal entry. Refuses (raises) an unbalanced entry — this is the
        first line of defence; Mahsa's LEDGER-001 is the backstop on aggregate state."""
        if len(lines) < 2:
            raise ValueError("a journal entry needs at least two lines")
        if not ledger_calc.is_balanced(lines):
            raise ValueError("journal entry is not balanced (total debits != total credits)")

        total_debit = sum(int(ln.get("debit", 0)) for ln in lines)
        total_credit = sum(int(ln.get("credit", 0)) for ln in lines)
        entry = JournalEntry(
            entry_date=entry_date,
            description=description,
            reference=reference,
            source=source,
            total_debit=total_debit,
            total_credit=total_credit,
            is_auto_generated=0 if source == "manual" else 1,
        )
        session.add(entry)
        session.flush()
        for ln in lines:
            session.add(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=int(ln["account_id"]),
                    debit=int(ln.get("debit", 0)),
                    credit=int(ln.get("credit", 0)),
                    description=ln.get("description"),
                )
            )
        session.flush()
        return {
            "journal_entry_id": entry.id,
            "total_debit": total_debit,
            "total_credit": total_credit,
        }

    # ---- statements -----------------------------------------------------------------

    def _typed_lines(self, session: Session) -> list[dict]:
        types = {a.id: a.account_type for a in session.scalars(select(ChartOfAccounts)).all()}
        return [
            {
                "account_type": types.get(ln.account_id, "asset"),
                "debit": int(ln.debit),
                "credit": int(ln.credit),
            }
            for ln in session.scalars(select(JournalLine)).all()
        ]

    def trial_balance(self, session: Session) -> dict[str, Any]:
        lines = [{"debit": r["debit"], "credit": r["credit"]} for r in self._typed_lines(session)]
        return ledger_calc.trial_balance(lines)

    def profit_and_loss(self, session: Session) -> dict[str, int]:
        return ledger_calc.profit_and_loss(self._typed_lines(session))

    def balance_sheet(self, session: Session) -> dict[str, Any]:
        return ledger_calc.balance_sheet(self._typed_lines(session))

    # ---- depreciation ---------------------------------------------------------------

    def annual_depreciation(self, session: Session, asset_id: int) -> int:
        asset = session.get(FixedAsset, asset_id)
        if asset is None:
            raise ValueError(f"fixed asset {asset_id} not found")
        if asset.depreciation_method == "slm":
            return ledger_calc.slm_annual(
                asset.purchase_cost, asset.salvage_value, asset.useful_life_years
            )
        return ledger_calc.wdv_annual(asset.wdv, asset.depreciation_rate)

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        tb = self.trial_balance(session)
        pnl = self.profit_and_loss(session)
        return {
            "as_of": anchor.isoformat(),
            "metrics": {
                # consumed by LEDGER-001 (must be 0)
                "trial_balance_diff_paise": tb["diff"],
                "net_profit_paise": pnl["net_profit"],
            },
        }
