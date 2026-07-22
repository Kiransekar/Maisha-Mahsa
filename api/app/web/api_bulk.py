"""JSON bulk-op endpoint for the Exception Inbox SPA (WS7.5 / research T3, anti-pattern #3 —
Xero's missing bulk-accept, 243 votes over 3+ years).

Thin wrapper over the SAME pure logic the HTMX flow uses (``app.web.exceptions.preview_bulk`` +
``app.core.approvals.record_decision``), so the SPA and the server-rendered inbox can never drift
into two different truths about what a bulk action would do.

Two honesty rules this endpoint adds on top of ``preview_bulk``:

1. **Nothing is silently dropped.** ``preview_bulk`` only sees ids that exist in the current
   inbox, so an id the caller sent that has since been resolved (or was never real) would
   vanish from both ``rows`` and ``skipped``. Here every submitted id is accounted for, each
   skipped one carrying the reason it was skipped.
2. **Never invent a ₹.** ``preview_bulk`` sums ``impact_paise or 0``; a set of rows whose impact
   is genuinely unknown would therefore total a very confident ``0``. Here the total is ``null``
   when no eligible row has a known impact, with ``unquantified_rows`` saying how many are
   unknown — "not yet known", never a fabricated zero.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.approvals import record_decision
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import enforce, require
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.web.exceptions import (
    _BULK_ACTIONS,  # single source of truth for the valid actions — do not re-declare
    InboxItem,
    build_items,
)
from app.web.exceptions import preview_bulk as _preview_bulk
from app.web.exceptions_router import collect_sources

router = APIRouter(prefix="/api", tags=["spa"])

_registry = build_registry()


class BulkRequest(BaseModel):
    action: str
    ids: list[str] = Field(default_factory=list)
    confirm: bool = False  # default dry-run: a preview must never mutate


def _skip_reason(item: InboxItem | None, action: str) -> str:
    """Why this selected row will not change. Never a bare 'not eligible'."""
    if item is None:
        return (
            "No longer in the inbox — it may already have been resolved, or the id is unknown. "
            "Nothing was changed for it."
        )
    if item.queue == "mahsa_blocked":
        return (
            "Mahsa's recompute did not match this figure. A blocked figure must be corrected, "
            "never bulk-waved through."
        )
    if not item.selectable:
        return "This item is not eligible for a bulk decision."
    return f"Bulk {action} applies only to items awaiting sign-off; this one is in '{item.queue}'."


def _mahsa_down(committed_count: int) -> dict[str, Any]:
    """Mahsa unreachable is STATED, never absorbed into a thinner response."""
    return {
        "mahsa_up": False,
        "committed": False,
        "action": None,
        "rows": [],
        "skipped": [],
        "total_impact_paise": None,
        "unquantified_rows": 0,
        "committed_count": committed_count,
        "note": (
            "Mahsa is unreachable, so no figure can be recomputed and nothing was changed."
            if committed_count == 0
            else (
                f"Mahsa became unreachable partway through: {committed_count} decision(s) were "
                "already sealed to the audit chain before it dropped. The rest were not applied."
            )
        ),
    }


@router.post("/inbox/bulk")
async def inbox_bulk_json(
    req: BulkRequest,
    request: Request,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(require(Capability.READ)),
) -> dict[str, Any]:
    """Preview-then-confirm bulk decision. ``confirm=false`` (the default) is a pure dry-run.

    WS5.1 — the preview and the commit are the same route but NOT the same permission. Reading
    what a bulk action *would* do needs ``read``; actually sealing decisions to the audit chain
    needs ``approve_payment``. So an Accountant can size up a bulk accept and cannot perform one.
    The commit gate is checked BEFORE any decision is recorded, not after the first one.
    """
    if req.action not in _BULK_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown bulk action {req.action!r}. Nothing was changed. "
                f"Valid actions: {', '.join(sorted(_BULK_ACTIONS))}."
            ),
        )

    as_of = datetime.now(UTC).date()
    committed_count = 0
    items: list[InboxItem] = []
    try:
        approvals, blocked, _ = await collect_sources(db, mahsa, as_of)
        items = build_items(approvals, blocked)
        preview = _preview_bulk(items, req.ids, req.action)  # dry-run — nothing mutated yet

        if req.confirm:
            enforce(principal, Capability.APPROVE_PAYMENT, request.url.path)
        if req.confirm and preview.rows:
            decision = _BULK_ACTIONS[req.action]
            user_id = principal.user_id
            for row in preview.rows:
                await record_decision(
                    db,
                    domain=row.domain,
                    decision=decision,
                    mahsa=mahsa,
                    registry=_registry,
                    as_of=as_of,
                    user_id=user_id,
                )
                committed_count += 1
            preview = replace(preview, committed=True)
    except MahsaError:
        return _mahsa_down(committed_count)

    # Account for every submitted id: anything neither eligible nor already skipped was dropped
    # by preview_bulk because it is not in the current inbox. Report it, don't lose it.
    by_id = {i.id: i for i in items}
    seen = {r.id for r in preview.rows} | {r.id for r in preview.skipped}
    skipped = [
        {**asdict(r), "reason": _skip_reason(by_id.get(r.id), req.action)} for r in preview.skipped
    ]
    skipped += [
        {
            "id": missing,
            "domain": "",
            "what": "Not found in the current inbox",
            "impact_paise": None,
            "will": "Nothing — this id was not acted on",
            "reason": _skip_reason(None, req.action),
        }
        for missing in req.ids
        if missing not in seen
    ]

    quantified = [r for r in preview.rows if r.impact_paise is not None]
    return {
        "mahsa_up": True,
        "action": preview.action,
        "rows": [asdict(r) for r in preview.rows],
        "skipped": skipped,
        # None (not 0) when nothing eligible has a known ₹ impact — we don't guess.
        "total_impact_paise": preview.total_impact_paise if quantified else None,
        "unquantified_rows": len(preview.rows) - len(quantified),
        "committed": preview.committed,
        "committed_count": committed_count,
        "as_of": as_of.isoformat(),
    }
