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
        is_cash: bool = False,
        is_bank: bool = False,
    ) -> int:
        if account_type not in (*ledger_calc.DEBIT_NATURED, *ledger_calc.CREDIT_NATURED):
            raise ValueError(f"invalid account_type: {account_type}")
        acct = ChartOfAccounts(
            code=code,
            name=name,
            account_type=account_type,
            sub_type=sub_type,
            opening_balance=opening_balance,
            is_cash_account=1 if is_cash else 0,
            is_bank_account=1 if is_bank else 0,
        )
        session.add(acct)
        session.flush()
        return acct.id

    def auto_post(
        self,
        session: Session,
        *,
        source: str,
        entry_date: str,
        description: str,
        lines: list[dict],
        reference: str | None = None,
    ) -> dict[str, Any]:
        """Post a system-generated entry from another module (payroll/gst/revenue). Tags the
        entry with its ``source`` (which flags ``is_auto_generated``); use ``ledger_calc``'s
        ``payroll_journal`` / ``sales_journal`` / ``gst_payment_journal`` to build the lines."""
        if source == "manual":
            raise ValueError("auto_post requires a non-manual source (e.g. payroll/gst/revenue)")
        return self.post_journal_entry(
            session,
            entry_date=entry_date,
            description=description,
            lines=lines,
            source=source,
            reference=reference,
        )

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

    def general_ledger(self, session: Session, account_id: int) -> dict[str, Any]:
        """Account-wise general ledger: every posting to the account in date order with a
        running balance (opening + cumulative debit − credit)."""
        acct = session.get(ChartOfAccounts, account_id)
        if acct is None:
            raise ValueError(f"account {account_id} not found")
        rows = session.execute(
            select(JournalLine, JournalEntry.entry_date)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(JournalLine.account_id == account_id)
            .order_by(JournalEntry.entry_date.asc(), JournalLine.id.asc())
        ).all()
        balance = int(acct.opening_balance)
        lines: list[dict[str, Any]] = []
        for jl, entry_date in rows:
            balance += int(jl.debit) - int(jl.credit)
            lines.append(
                {
                    "date": entry_date,
                    "description": jl.description,
                    "debit": int(jl.debit),
                    "credit": int(jl.credit),
                    "balance": balance,
                }
            )
        return {
            "account_id": account_id,
            "code": acct.code,
            "name": acct.name,
            "opening_balance": int(acct.opening_balance),
            "lines": lines,
            "closing_balance": balance,
        }

    def cash_flow(self, session: Session) -> dict[str, int]:
        """Direct-method cash-flow statement. Each entry's net cash movement is classified by
        its non-cash counterpart: income/expense → operating, asset → investing, equity/
        liability → financing. Requires cash/bank accounts to be flagged (``is_cash``)."""
        accounts = {a.id: a for a in session.scalars(select(ChartOfAccounts)).all()}
        cash_ids = {
            aid for aid, a in accounts.items() if a.is_cash_account or a.is_bank_account
        }
        flows = {"operating": 0, "investing": 0, "financing": 0, "net_change": 0}
        if not cash_ids:
            return flows
        _bucket = {
            "income": "operating", "expense": "operating",
            "asset": "investing", "liability": "financing", "equity": "financing",
        }
        for entry in session.scalars(select(JournalEntry)).all():
            lines = session.scalars(
                select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
            ).all()
            cash_delta = sum(
                int(line.debit) - int(line.credit)
                for line in lines
                if line.account_id in cash_ids
            )
            non_cash = [line for line in lines if line.account_id not in cash_ids]
            if cash_delta == 0 or not non_cash:
                continue
            counterpart = max(non_cash, key=lambda line: int(line.debit) + int(line.credit))
            bucket = _bucket.get(accounts[counterpart.account_id].account_type, "operating")
            flows[bucket] += cash_delta
        flows["net_change"] = flows["operating"] + flows["investing"] + flows["financing"]
        return flows

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
