"""P1-4 — investor-update preview JSON for the SPA /cfo screen.

Thin wrapper over the SAME ``app.core.strategy.investor_update`` generator the HTMX
/investor and /cfo pages render — nothing re-derived here, so the two surfaces cannot
drift into two truths. Sending stays on the HTMX/email surface (``POST /investor/send``);
this module deliberately wires NO send path — the SPA links out.

Honesty (docs/WS7_BUILD_CONTRACT.md):
  · every money figure is badged through ``app.core.mahsa_coverage.badge_state`` (§0.4) —
    no KPI key is Mahsa-ported today, so each honestly ships ``honest_pending``, never a
    hardcoded ✓;
  · the null-runway / empty-ledger distinction (the WS7-E2E fix) SURVIVES to the payload:
    it carries ``runway_months`` + ``accounts`` raw — never the pre-baked "∞" string the
    email template uses — so the SPA's existing ``runwayText`` logic decides the honest
    sentence ("no ledger yet" vs "not yet known — we don't guess").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.mahsa_coverage import badge_state
from app.core.overview import collect_kpis
from app.core.rbac import Capability
from app.core.rbac_deps import require
from app.core.strategy import investor_update
from app.db.session import get_session
from app.web.format import fmt_value, humanize

# WS5.1: `read` baseline — the preview is read-only; nothing here mutates or sends.
router = APIRouter(
    prefix="/api/investor",
    tags=["investor"],
    dependencies=[Depends(require(Capability.READ))],
)


class PreviewBody(BaseModel):
    highlights: list[str] = Field(default_factory=list)


def _figure(key: str, paise: int) -> dict[str, Any]:
    """One badged figure — the api_statements assembler pattern, never hardcoded verified."""
    return {
        "key": key,
        "label": humanize(key),
        "value": fmt_value(key, paise),
        "raw": paise,
        "state": badge_state(key),
    }


@router.post("/preview")
def preview(body: PreviewBody, db: Session = Depends(get_session)) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    highlights = [h.strip() for h in body.highlights if h.strip()]
    upd = investor_update(db, today, highlights=highlights)
    # Same deterministic reads investor_update just made — fetched again only because the
    # composed payload carries "∞" instead of the raw runway facts the SPA needs to be honest.
    kpis = collect_kpis(db, today)
    return {
        "period": upd["period"],
        "figures": [
            _figure("cash_paise", upd["cash"]),
            _figure("net_burn_paise", upd["net_burn"]),
            _figure("ar_paise", upd["ar"]),
        ],
        "runway_months": kpis["runway_months"],
        "accounts": kpis["accounts"],
        "cap_table": upd["cap_table"],
        "highlights": upd["highlights"],
        # Sending is the HTMX/email surface's job — the SPA links there, it never sends.
        "send_via": "/investor",
    }
