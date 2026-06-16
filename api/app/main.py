"""FastAPI application factory. Wires the domain routers, the dashboard, health, and the
static/template assets. Creates the schema on startup for local/dev use."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.cfo_router import router as cfo_router
from app.config import get_settings
from app.core.cfo import DomainHealth, collect_health
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.overview import collect_kpis, upcoming_deadlines
from app.db import models as _models  # noqa: F401  registers all models on Base.metadata
from app.db.base import Base
from app.db.session import get_session, session_factory
from app.domains import build_registry
from app.domains.compliance.router import router as compliance_router
from app.domains.equity.router import router as equity_router
from app.domains.expense.router import router as expense_router
from app.domains.forecast.router import router as forecast_router
from app.domains.gst.router import router as gst_router
from app.domains.ledger.router import router as ledger_router
from app.domains.payables.router import router as payables_router
from app.domains.payroll.router import router as payroll_router
from app.domains.revenue.router import router as revenue_router
from app.domains.tax.router import router as tax_router
from app.domains.treasury.router import router as treasury_router
from app.domains.vault.router import router as vault_router

_WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(_WEB / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)

    # Ensure the schema exists (dev convenience; production uses Alembic migrations).
    Base.metadata.create_all(bind=session_factory().kw["bind"])

    app.mount("/static", StaticFiles(directory=str(_WEB / "static")), name="static")
    app.include_router(treasury_router)
    app.include_router(payroll_router)
    app.include_router(gst_router)
    app.include_router(revenue_router)
    app.include_router(payables_router)
    app.include_router(tax_router)
    app.include_router(ledger_router)
    app.include_router(compliance_router)
    app.include_router(equity_router)
    app.include_router(forecast_router)
    app.include_router(expense_router)
    app.include_router(vault_router)
    app.include_router(cfo_router)

    registry = build_registry()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": settings.version}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, db: Session = Depends(get_session)) -> HTMLResponse:
        today = datetime.now(UTC).date()
        # KPI strip + compliance calendar are direct DB reads (no Mahsa dependency).
        kpis = collect_kpis(db, today)
        calendar = upcoming_deadlines(db, today)

        # Live domain health from Mahsa; degrade gracefully if the sidecar is unreachable.
        health_by_domain: dict[str, DomainHealth] = {}
        mahsa_up = True
        try:
            mahsa = MahsaClient(settings.mahsa_url)
            for h in await collect_health(db, mahsa, registry):
                health_by_domain[h.domain] = h
        except MahsaError:
            mahsa_up = False

        domains = []
        approvals = []
        for d in registry.domains():
            dh = health_by_domain.get(d)
            domains.append(
                {
                    "key": d,
                    "score": dh.score if dh else None,
                    "status": dh.status if dh else None,
                    "color": dh.color if dh else None,
                }
            )
            if dh and dh.requires_approval:
                approvals.append(
                    {"domain": d, "status": dh.status, "color": dh.color, "banners": dh.banners}
                )

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "domains": domains,
                "settings": settings,
                "mahsa_up": mahsa_up,
                "kpis": kpis,
                "calendar": calendar,
                "approvals": approvals,
            },
        )

    return app


app = create_app()
