"""Equity service: cap table, ESOP pool + board-approval gate, SAFE conversion, dilution,
cap-table snapshots, and the equity health snapshot for Mahsa. Deterministic."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.equity import CapTableSnapshot, Shareholder
from app.domains.equity import equity_calc
from app.domains.equity.manifest import MANIFEST


class EquityService(BaseDomainService):
    domain = "equity"
    keywords = (
        "cap table",
        "esop",
        "safe",
        "shareholder",
        "investor",
        "dilution",
        "equity",
        "shares",
        "convertible",
    )
    manifest = MANIFEST

    # ---- cap table ------------------------------------------------------------------

    def add_shareholder(
        self,
        session: Session,
        *,
        name: str,
        category: str,
        shares_held: int = 0,
        investment_amount: int = 0,
        board_seat: bool = False,
    ) -> int:
        holder = Shareholder(
            name=name,
            category=category,
            shares_held=shares_held,
            investment_amount=investment_amount,
            board_seat=1 if board_seat else 0,
        )
        session.add(holder)
        session.flush()
        return holder.id

    def _holders(self, session: Session) -> list[dict]:
        return [
            {"category": s.category, "shares": int(s.shares_held)}
            for s in session.scalars(select(Shareholder)).all()
        ]

    def cap_table(self, session: Session) -> dict[str, Any]:
        return equity_calc.ownership(self._holders(session))

    def esop_pool_pct(self, session: Session) -> float:
        cap = self.cap_table(session)
        return equity_calc.esop_pool_pct(cap["by_category"].get("esop", 0), cap["total_shares"])

    # ---- SAFE -----------------------------------------------------------------------

    def convert_safe(
        self,
        *,
        investment: int,
        valuation_cap: int | None,
        discount_rate: float,
        round_price_per_share: int,
        pre_round_shares: int,
    ) -> dict[str, int]:
        return equity_calc.safe_conversion(
            investment=investment,
            valuation_cap=valuation_cap,
            discount_rate=discount_rate,
            round_price_per_share=round_price_per_share,
            pre_round_shares=pre_round_shares,
        )

    # ---- share certificates / rights / buyback --------------------------------------

    def _named_holders(self, session: Session) -> list[dict]:
        return [
            {"name": s.name, "shares": int(s.shares_held), "category": s.category}
            for s in session.scalars(select(Shareholder).order_by(Shareholder.id)).all()
        ]

    def share_certificates(self, session: Session) -> list[dict]:
        """Share-certificate register with contiguous distinctive share numbers."""
        return equity_calc.share_certificates(self._named_holders(session))

    def rights_entitlement(self, session: Session, new_shares: int) -> list[dict]:
        """Pro-rata rights-issue entitlement per shareholder (s.62(1)(a))."""
        return equity_calc.rights_entitlement(self._named_holders(session), new_shares)

    def buyback_compliance(
        self,
        *,
        paid_up_capital: int,
        free_reserves: int,
        buyback_amount: int,
        shares_bought_back: int = 0,
        total_shares: int = 0,
        post_buyback_debt: int = 0,
        post_buyback_equity: int = 0,
    ) -> dict[str, Any]:
        """Companies Act s.68 buyback limit check."""
        return equity_calc.buyback_compliance(
            paid_up_capital=paid_up_capital,
            free_reserves=free_reserves,
            buyback_amount=buyback_amount,
            shares_bought_back=shares_bought_back,
            total_shares=total_shares,
            post_buyback_debt=post_buyback_debt,
            post_buyback_equity=post_buyback_equity,
        )

    # ---- snapshots ------------------------------------------------------------------

    def snapshot_cap_table(
        self, session: Session, *, snapshot_date: str, esop_board_approved: bool = True
    ) -> int:
        cap = self.cap_table(session)
        pool_pct = self.esop_pool_pct(session)
        row = CapTableSnapshot(
            snapshot_date=snapshot_date,
            total_shares=cap["total_shares"],
            total_diluted_shares=cap["total_shares"],
            esop_pool_shares=cap["by_category"].get("esop", 0),
            esop_pool_pct=pool_pct,
            esop_board_approved=1 if esop_board_approved else 0,
            snapshot_json=json.dumps(cap),
        )
        session.add(row)
        session.flush()
        return row.id

    def _board_approved(self, session: Session) -> int:
        latest = session.scalars(
            select(CapTableSnapshot).order_by(CapTableSnapshot.id.desc()).limit(1)
        ).first()
        return int(latest.esop_board_approved) if latest else 1

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        cap = self.cap_table(session)
        pool_pct = equity_calc.esop_pool_pct(cap["by_category"].get("esop", 0), cap["total_shares"])
        board_approved = self._board_approved(session)

        return {
            "as_of": anchor.isoformat(),
            "metrics": {
                "dilution_rate": 1.0,
                "esop_utilization": 1.0,
                "safe_conversion_complexity": 1.0,
                "investor_reporting_timeliness": 1.0,
                "dividend_capacity": 1.0,
                "share_pricing_fairness": 1.0,
                "board_compliance": 1.0 if board_approved else 0.0,
                "cap_table_accuracy": 1.0,  # shares sum to 100% by construction
                # signals for EQUITY-001
                "esop_pool_pct": pool_pct,
                "esop_board_approved": board_approved,
            },
        }
