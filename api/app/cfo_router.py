"""CFO routes: the cross-domain health brief (JSON + rendered email preview + dispatch)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.cfo import brief_payload, collect_health, compose_brief
from app.core.email.channel import EmailChannel
from app.core.email.renderer import render_daily_brief
from app.core.email.transport import SmtpTransport
from app.core.mahsa_client import MahsaClient
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry

router = APIRouter(prefix="/cfo", tags=["cfo"])


async def _brief(session: Session, mahsa: MahsaClient, as_of: str | None):
    anchor = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    health = await collect_health(session, mahsa, build_registry(), as_of=anchor)
    return compose_brief(anchor.isoformat(), health)


@router.get("/brief")
async def brief_json(
    as_of: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict:
    return brief_payload(await _brief(db, mahsa, as_of))


@router.get("/brief.html", response_class=HTMLResponse)
async def brief_html(
    as_of: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> HTMLResponse:
    settings = get_settings()
    brief = await _brief(db, mahsa, as_of)
    return HTMLResponse(render_daily_brief(brief, company_name=settings.app_name))


@router.post("/brief/send")
async def brief_send(
    to: str | None = None,
    as_of: str | None = None,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict:
    settings = get_settings()
    brief = await _brief(db, mahsa, as_of)
    channel = EmailChannel(
        SmtpTransport(host=settings.smtp_host, port=settings.smtp_port),
        sender=settings.email_sender,
    )
    await channel.send_daily_brief(
        to=to or settings.cfo_email, brief=brief, company_name=settings.app_name
    )
    return {"sent_to": to or settings.cfo_email, "needs_attention": len(brief.needs_attention)}
