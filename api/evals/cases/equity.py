"""Equity eval cases. Cap table of 10,00,000 shares with a 1,00,000-share ESOP pool → a 10%
pool. Ground truth mirrors ``tests/unit/equity/test_equity_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domains.equity.service import EquityService
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_cap_table(session: Session) -> None:
    svc = EquityService()
    svc.add_shareholder(session, name="Founder", category="founder", shares_held=700000)
    svc.add_shareholder(session, name="VC", category="investor", shares_held=200000)
    svc.add_shareholder(session, name="ESOP Pool", category="esop", shares_held=100000)


CASES: list[EvalCase] = [
    EvalCase(
        id="equity-esop-pool",
        domain="equity",
        query="What fraction of the cap table is the ESOP pool?",
        seed=_seed_cap_table,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"esop_pool_pct": "0.1"},  # 1,00,000 / 10,00,000
        ),
        stub_claim=ActionClaim(
            domain="equity",
            narrative="The ESOP pool is 1,00,000 of 10,00,000 shares — 10% of the cap table.",
            claims={"esop_pool_pct": "0.1"},
        ),
    ),
]
