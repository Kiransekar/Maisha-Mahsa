"""Exception Inbox routes (WS7.5). Thin: fetches the real sources (pending approvals + a Mahsa
recompute fold per domain for blocked figures), hands them to the pure assembler, and renders.
The bulk-op endpoint returns a PREVIEW (dry-run) and only mutates when confirm=true (research #1
anti-pattern: never a silent bulk mutation)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.approvals import pending_approvals, record_decision
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.money import Paise
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.web.exceptions import (
    ApprovalInput,
    BlockedFigureInput,
    build_inbox,
    build_items,
    preview_bulk,
)

router = APIRouter(tags=["inbox"])

_WEB = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_WEB / "templates"))
templates.env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()

_registry = build_registry()


def _snapshot(service: Any, session: Session, as_of: date | None) -> dict[str, Any]:
    try:
        return service.build_snapshot(session, as_of)
    except TypeError:
        return service.build_snapshot(session)


def _claims(service: Any, session: Session, as_of: date | None) -> list[Any]:
    try:
        return service.recompute_claims(session, as_of)
    except TypeError:
        return service.recompute_claims(session)


async def _collect(
    session: Session, mahsa: MahsaClient, as_of: date | None
) -> tuple[list[ApprovalInput], list[BlockedFigureInput], bool]:
    """Fetch the two wired sources. Blocked figures come from folding each domain WITH its
    recompute claims and keeping the checks Mahsa could recompute but that did NOT match."""
    approvals: list[ApprovalInput] = []
    blocked: list[BlockedFigureInput] = []
    amounts: dict[str, int] = {}
    for domain in _registry.domains():
        service = _registry.get(domain)
        if service is None:
            continue
        snapshot = _snapshot(service, session, as_of)
        claims = _claims(service, session, as_of)
        if not claims:
            continue
        amounts[domain] = max((int(c.claimed_paise) for c in claims), default=0)
        fold = await mahsa.fold(snapshot, domain=domain, recompute_claims=claims)
        for chk in fold.recompute:
            if not chk.matches and not chk.honest_pending:
                blocked.append(
                    BlockedFigureInput(
                        domain=domain,
                        target=chk.target,
                        label=chk.label,
                        claimed_paise=int(chk.claimed_paise),
                        recomputed_paise=chk.recomputed_paise,
                        note=chk.note,
                    )
                )
    for a in await pending_approvals(session, mahsa, _registry, as_of=as_of):
        approvals.append(
            ApprovalInput(
                domain=a.domain,
                status=a.status,
                resolution=a.resolution,
                amount_paise=amounts.get(a.domain),
            )
        )
    return approvals, blocked, True


@router.get("/inbox", response_class=HTMLResponse)
async def inbox_page(
    request: Request,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> HTMLResponse:
    today = datetime.now(UTC).date()
    mahsa_up = True
    try:
        approvals, blocked, mahsa_up = await _collect(db, mahsa, today)
        inbox = build_inbox(build_items(approvals, blocked))
    except MahsaError:
        mahsa_up = False
        inbox = build_inbox([])
    return templates.TemplateResponse(
        request,
        "exception_inbox.html",
        {
            "inbox": inbox,
            "mahsa_up": mahsa_up,
            "settings": get_settings(),
            "nav_active": "inbox",
        },
    )


@router.post("/inbox/bulk", response_class=HTMLResponse)
async def inbox_bulk(
    request: Request,
    action: str = Form(...),
    ids: list[str] = Form(default=[]),
    confirm: bool = Form(default=False),
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> HTMLResponse:
    today = datetime.now(UTC).date()
    toast = None
    mahsa_up = True
    try:
        approvals, blocked, mahsa_up = await _collect(db, mahsa, today)
        items = build_items(approvals, blocked)
        preview = preview_bulk(items, ids, action)  # dry-run — nothing mutated yet
        if confirm and preview.rows:
            settings = get_settings()
            decision = "approved" if action == "approve" else "rejected"
            for row in preview.rows:
                await record_decision(
                    db,
                    domain=row.domain,
                    decision=decision,
                    mahsa=mahsa,
                    registry=_registry,
                    as_of=today,
                    user_id=settings.default_user_id,
                )
            toast = f"{len(preview.rows)} item(s) {decision} · sealed to the audit chain."
            preview = replace(preview, committed=True)
    except MahsaError:
        mahsa_up = False
        preview = None
        toast = "Mahsa offline — nothing changed."
    except ValueError as exc:
        preview = None
        toast = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/inbox_bulk_preview.html",
        {"preview": preview, "toast": toast, "mahsa_up": mahsa_up},
    )
