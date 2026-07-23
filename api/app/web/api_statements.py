"""P1-5 — financial-statements JSON for the SPA /statements screen.

Thin wrapper over the SAME ``LedgerService`` methods the existing ``/api/ledger`` GET
endpoints call — nothing is re-derived here. Every money figure is badged through
``app.core.mahsa_coverage.badge_state`` (§0.4), the identical assembler pattern
``api_domains._figure`` uses: a figure is ``verified`` only if Mahsa's Rust engine
independently recomputes that fact key. No ledger statement key is Mahsa-ported today,
so every figure here honestly ships ``honest_pending`` — never a hardcoded ✓.

A broken book must look broken (docs/WS7_BUILD_CONTRACT.md): the trial-balance
``balanced`` flag and the balance-sheet equation flag pass through to the payload
untouched; this layer never "corrects" or hides an imbalance, and the SPA renders the
failure as an explicit banner.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.mahsa_coverage import badge_state
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.db.models.ledger import ChartOfAccounts
from app.db.session import get_session
from app.domains.ledger.service import LedgerService
from app.web.format import fmt_value, humanize

# WS5.1: `read` baseline on every route — statements are read-only, no mutation lives here.
router = APIRouter(
    prefix="/api/statements",
    tags=["statements"],
    dependencies=[Depends(require(Capability.READ))],
)

_service = LedgerService()


def _figure(key: str, paise: int) -> dict[str, Any]:
    """One statement figure with its honest coverage badge — never hardcoded verified."""
    return {
        "key": key,
        "label": humanize(key),
        "value": fmt_value(key, paise),
        "raw": paise,
        "state": badge_state(key),
    }


@router.get("")
def statements(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Trial balance + P&L + balance sheet (each money figure badged) and the chart of
    accounts for the general-ledger drilldown picker."""
    tb = _service.trial_balance(db)
    pnl = _service.profit_and_loss(db)
    bs = _service.balance_sheet(db)
    accounts = db.scalars(select(ChartOfAccounts).order_by(ChartOfAccounts.code)).all()
    return {
        "as_of": datetime.now(UTC).date().isoformat(),
        "trial_balance": {
            # the imbalance flag SURVIVES to the payload — the SPA's banner hangs off it
            "balanced": bool(tb["balanced"]),
            "figures": [
                _figure("total_debit_paise", tb["total_debit"]),
                _figure("total_credit_paise", tb["total_credit"]),
                _figure("trial_balance_diff_paise", tb["diff"]),
            ],
        },
        "pnl": {
            "figures": [
                _figure("income_paise", pnl["income"]),
                _figure("expense_paise", pnl["expense"]),
                _figure("net_profit_paise", pnl["net_profit"]),
            ],
        },
        "balance_sheet": {
            "balanced": bool(bs["balanced"]),
            "figures": [
                _figure("assets_paise", bs["assets"]),
                _figure("liabilities_paise", bs["liabilities"]),
                _figure("equity_paise", bs["equity"]),
                _figure("retained_profit_paise", bs["retained_profit"]),
            ],
        },
        "accounts": [
            {"id": a.id, "code": a.code, "name": a.name, "account_type": a.account_type}
            for a in accounts
        ],
    }


@router.get("/gl/{account_id}")
def general_ledger(account_id: int, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Account drilldown: every posting in date order with a running balance."""
    try:
        gl = _service.general_ledger(db, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "account_id": gl["account_id"],
        "code": gl["code"],
        "name": gl["name"],
        "opening": _figure("opening_balance_paise", gl["opening_balance"]),
        "closing": _figure("closing_balance_paise", gl["closing_balance"]),
        # one payload-decided badge for the entry rows' running-balance column (§0.4 —
        # the SPA renders this state, it never invents its own)
        "state": badge_state("general_ledger_balance_paise"),
        "lines": gl["lines"],
    }
