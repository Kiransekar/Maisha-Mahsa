"""WS7.3 — the Today view route. Thin: fetch the pending approvals (the one async, Mahsa-backed
input) and hand everything to the pure ``build_today`` assembler. Its own Jinja env avoids a
circular import with app.main (which will ``include_router`` this)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.approvals import pending_approvals
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.money import Paise
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.web.today import build_today

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()

router = APIRouter(tags=["today"])


@router.get("/today", response_class=HTMLResponse)
async def today_page(
    request: Request,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> HTMLResponse:
    as_of = datetime.now(UTC).date()
    mahsa_up = True
    try:
        approvals = await pending_approvals(db, mahsa, build_registry(), as_of=as_of)
    except MahsaError:
        approvals = []
        mahsa_up = False

    view = build_today(db, as_of, approvals)
    return _TEMPLATES.TemplateResponse(
        request,
        "today.html",
        {**view, "settings": get_settings(), "mahsa_up": mahsa_up, "nav_active": "today"},
    )
