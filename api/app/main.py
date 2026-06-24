"""FastAPI application factory. Wires the domain routers, the dashboard, health, and the
static/template assets. Creates the schema on startup for local/dev use."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.cfo_router import router as cfo_router
from app.config import get_settings
from app.core import history_store, parallel, trace_store
from app.core.approvals import pending_approvals, record_decision
from app.core.ask import answer_query
from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.cfo import DomainHealth, collect_health
from app.core.domain import BaseDomainService
from app.core.email.channel import EmailChannel
from app.core.email.transport import SmtpTransport
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.money import Paise
from app.core.ocr import OcrUnavailable
from app.core.overview import collect_kpis, upcoming_deadlines
from app.core.strategy import cap_table as cfo_cap_table
from app.core.strategy import investor_update, run_scenario
from app.db import models as _models  # noqa: F401  registers all models on Base.metadata
from app.db.base import Base
from app.db.session import get_session, session_factory
from app.domains import build_registry
from app.domains.compliance.router import router as compliance_router
from app.domains.equity.router import router as equity_router
from app.domains.expense.router import router as expense_router
from app.domains.forecast.router import router as forecast_router
from app.domains.gst import gst_calc
from app.domains.gst.router import router as gst_router
from app.domains.ledger.router import router as ledger_router
from app.domains.payables.router import router as payables_router
from app.domains.payroll.router import router as payroll_router
from app.domains.payroll.service import PayrollService
from app.domains.revenue.router import router as revenue_router
from app.domains.revenue.service import RevenueService
from app.domains.tax.router import router as tax_router
from app.domains.treasury.router import router as treasury_router
from app.domains.vault.router import router as vault_router
from app.llm.tools import enrich
from app.web.actions import actions_for, find_action
from app.web.charts import sparkline
from app.web.format import fact_rows, humanize

_WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(_WEB / "templates"))
# `{{ amount_paise | rupees }}` -> Indian-grouped ₹ string (mirrors the email renderer).
templates.env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()


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
                "nav_active": "dashboard",
            },
        )

    @app.get("/d/{domain}", response_class=HTMLResponse)
    async def domain_page(
        domain: str, request: Request, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        service = registry.get(domain)
        if service is None:
            raise HTTPException(status_code=404, detail=f"unknown domain '{domain}'")
        today = datetime.now(UTC).date()
        try:
            snapshot = service.build_snapshot(db, today)  # type: ignore[call-arg]
        except TypeError:
            snapshot = service.build_snapshot(db)
        figures = fact_rows(enrich(snapshot))

        health = None
        citations: list[dict[str, str]] = []
        mahsa_up = True
        try:
            fold = await MahsaClient(settings.mahsa_url).fold(snapshot, domain=domain)
            shape = fold.shape
            score = shape.domain_score if shape.domain_score is not None else shape.global_score
            colour = {"green": "green", "yellow": "amber", "red": "red"}.get(
                fold.validation.status, "green"
            )
            health = {
                "status": fold.validation.status,
                "score": round(score, 1) if score is not None else None,
                "color": colour,
            }
            citations = [
                {"rule_id": t.id, "text": t.description, "citation": f"{t.statute} / {t.section}"}
                for t in fold.validation.triggered
            ]
        except MahsaError:
            mahsa_up = False

        # Real trend charts from captured history — only metrics with ≥2 points (no fabrication).
        trends = []
        for metric, points in history_store.domain_series(db, domain).items():
            svg = sparkline([v for _, v in points])
            if svg:
                trends.append({"label": humanize(metric), "svg": svg, "points": len(points)})

        return templates.TemplateResponse(
            request,
            "domain.html",
            {
                "domain": domain,
                "figures": figures,
                "health": health,
                "citations": citations,
                "mahsa_up": mahsa_up,
                "settings": settings,
                "actions": actions_for(domain),
                "trends": trends,
                "nav_active": domain,
            },
        )

    def _domain_figures(db: Session, service: BaseDomainService) -> list[Any]:
        today = datetime.now(UTC).date()
        try:
            snapshot = service.build_snapshot(db, today)  # type: ignore[call-arg]
        except TypeError:
            snapshot = service.build_snapshot(db)
        return fact_rows(enrich(snapshot))

    @app.get("/d/{domain}/action/{key}/form", response_class=HTMLResponse)
    async def action_form(domain: str, key: str, request: Request) -> HTMLResponse:
        action = find_action(domain, key)
        if action is None:
            raise HTTPException(status_code=404, detail="unknown action")
        return templates.TemplateResponse(
            request, "partials/drawer_form.html", {"action": action, "settings": settings}
        )

    @app.post("/d/{domain}/action/{key}", response_class=HTMLResponse)
    async def action_submit(
        domain: str, key: str, request: Request, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        action = find_action(domain, key)
        if action is None:
            raise HTTPException(status_code=404, detail="unknown action")
        service = registry.get(domain)
        assert service is not None
        form = await request.form()
        data = {k: str(v) for k, v in form.items()}
        try:
            message = action.handler(db, data)
            db.commit()
        except (ValueError, KeyError, TypeError) as exc:
            db.rollback()
            return templates.TemplateResponse(
                request,
                "partials/drawer_form.html",
                {"action": action, "error": str(exc) or "Invalid input", "settings": settings},
            )
        return templates.TemplateResponse(
            request,
            "partials/action_success.html",
            {"message": message, "figures": _domain_figures(db, service), "settings": settings},
        )

    def _pdf(content: bytes, filename: str) -> Response:
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    @app.get("/d/payroll/{employee_id}/payslip")
    async def payslip_pdf_route(
        employee_id: int, period: str, db: Session = Depends(get_session)
    ) -> Response:
        try:
            content = PayrollService().payslip(
                db, employee_id, period=period, company=settings.app_name
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _pdf(content, f"payslip-{employee_id}-{period}.pdf")

    @app.get("/d/payroll/{employee_id}/form16")
    async def form16_pdf_route(
        employee_id: int, fy: str, db: Session = Depends(get_session)
    ) -> Response:
        try:
            content = PayrollService().form16(
                db, employee_id, financial_year=fy, company=settings.app_name
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _pdf(content, f"form16-{employee_id}-{fy}.pdf")

    @app.get("/d/payroll/ecr.txt")
    async def payroll_ecr_route(period: str, db: Session = Depends(get_session)) -> Response:
        text = PayrollService().ecr_text(db, period=period)
        return Response(
            content=text,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="ecr-{period}.txt"'},
        )

    from app.domains.expense.service import ExpenseService
    from app.domains.vault.service import VaultService

    @app.post("/d/expense/ocr-receipt")
    async def expense_ocr_route(file: UploadFile = File(...)) -> dict[str, Any]:
        try:
            return ExpenseService().ocr_capture(await file.read())
        except OcrUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/d/vault/ocr-ingest")
    async def vault_ocr_route(
        file: UploadFile = File(...),
        upload_date: str = Form(...),
        db: Session = Depends(get_session),
    ) -> dict[str, Any]:
        try:
            result = VaultService().ingest_image(
                db, file_name=file.filename or "scan", image_bytes=await file.read(),
                upload_date=upload_date,
            )
            db.commit()
            return result
        except OcrUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/d/gst/einvoice.json")
    async def einvoice_route(invoice: str, db: Session = Depends(get_session)) -> Response:
        try:
            payload = RevenueService().einvoice(db, invoice, seller_gstin=settings.company_gstin)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="einvoice-{invoice}.json"'},
        )

    @app.get("/d/gst/gstr1.json")
    async def gstr1_json_route(period: str, db: Session = Depends(get_session)) -> Response:
        lines = RevenueService().gstr1_lines(db, period)
        payload = gst_calc.gstr1_json(
            lines, gstin=settings.company_gstin, filing_period=period
        )
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="gstr1-{period}.json"'},
        )

    @app.get("/ask", response_class=HTMLResponse)
    async def ask_page(
        request: Request, q: str | None = None, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        answer = (
            await answer_query(db, query=q, registry=registry, settings=settings, as_of=today)
            if q
            else None
        )
        return templates.TemplateResponse(
            request,
            "ask.html",
            {
                "answer": answer,
                "settings": settings,
                "mahsa_up": answer.mahsa_up if answer else True,
                "nav_active": "ask",
            },
        )

    @app.post("/ask", response_class=HTMLResponse)
    async def ask_partial(
        request: Request, q: str = Form(...), db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        answer = await answer_query(
            db, query=q, registry=registry, settings=settings, as_of=today
        )
        return templates.TemplateResponse(
            request, "partials/answer_card.html", {"answer": answer, "settings": settings}
        )

    @app.get("/approvals", response_class=HTMLResponse)
    async def approvals_page(
        request: Request, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        items = []
        mahsa_up = True
        try:
            items = await pending_approvals(
                db, MahsaClient(settings.mahsa_url), registry, as_of=today
            )
        except MahsaError:
            mahsa_up = False
        return templates.TemplateResponse(
            request,
            "approvals.html",
            {"items": items, "mahsa_up": mahsa_up, "settings": settings, "nav_active": "approvals"},
        )

    @app.post("/approvals/{domain}/decide", response_class=HTMLResponse)
    async def approvals_decide(
        domain: str,
        request: Request,
        decision: str = Form(...),
        db: Session = Depends(get_session),
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        mahsa = MahsaClient(settings.mahsa_url)
        toast = None
        mahsa_up = True
        try:
            toast = await record_decision(
                db,
                domain=domain,
                decision=decision,
                mahsa=mahsa,
                registry=registry,
                as_of=today,
                user_id=settings.default_user_id,
            )
            items = await pending_approvals(db, mahsa, registry, as_of=today)
        except MahsaError:
            items, mahsa_up = [], False
            toast = "Mahsa offline — decision not recorded."
        except ValueError as exc:
            db.rollback()
            items = await pending_approvals(db, mahsa, registry, as_of=today)
            toast = str(exc)
        return templates.TemplateResponse(
            request,
            "partials/approvals_list.html",
            {"items": items, "mahsa_up": mahsa_up, "toast": toast, "settings": settings},
        )

    def _scenario_view(s: Any) -> dict[str, str]:
        runway = "∞ (cash-flow positive)" if s.runway_months is None else f"{s.runway_months:g} mo"
        return {
            "net_fmt": Paise(s.monthly_net_change_paise).format_inr(),
            "min_cash_fmt": Paise(s.min_cash_paise).format_inr(),
            "runway_fmt": runway,
        }

    @app.get("/cfo", response_class=HTMLResponse)
    async def cfo_page(request: Request, db: Session = Depends(get_session)) -> HTMLResponse:
        today = datetime.now(UTC).date()
        scenario = run_scenario(db, today)
        return templates.TemplateResponse(
            request,
            "cfo.html",
            {
                "kpis": collect_kpis(db, today),
                "cap": cfo_cap_table(db),
                "investor": investor_update(db, today),
                "calendar": upcoming_deadlines(db, today),
                "s": _scenario_view(scenario),
                "settings": settings,
                "nav_active": "cfo",
            },
        )

    @app.post("/cfo/scenario", response_class=HTMLResponse)
    async def cfo_scenario(
        request: Request,
        revenue_mult: float = Form(1.0),
        extra_cost: float = Form(0.0),
        db: Session = Depends(get_session),
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        scenario = run_scenario(
            db,
            today,
            revenue_mult=revenue_mult,
            extra_cost_paise=int(Paise.from_rupees(extra_cost)),
        )
        return templates.TemplateResponse(
            request, "partials/scenario_result.html", {"s": _scenario_view(scenario)}
        )

    def _parse_highlights(raw: str) -> list[str]:
        return [line.strip() for line in raw.splitlines() if line.strip()]

    @app.get("/investor", response_class=HTMLResponse)
    async def investor_page(request: Request, db: Session = Depends(get_session)) -> HTMLResponse:
        today = datetime.now(UTC).date()
        return templates.TemplateResponse(
            request,
            "investor.html",
            {"upd": investor_update(db, today), "settings": settings, "nav_active": "investor"},
        )

    @app.post("/investor/preview", response_class=HTMLResponse)
    async def investor_preview(
        request: Request, highlights: str = Form(""), db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        upd = investor_update(db, today, highlights=_parse_highlights(highlights))
        return templates.TemplateResponse(
            request, "partials/investor_preview.html", {"upd": upd, "settings": settings}
        )

    @app.post("/investor/send", response_class=HTMLResponse)
    async def investor_send(
        request: Request, highlights: str = Form(""), db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        ctx = investor_update(db, today, highlights=_parse_highlights(highlights))
        channel = EmailChannel(
            SmtpTransport(host=settings.smtp_host, port=settings.smtp_port),
            sender=settings.email_sender,
        )
        try:
            await channel.send_investor_update(
                to=settings.cfo_email, ctx=ctx, company_name=settings.app_name
            )
            message = f"Investor update ({ctx['period']}) sent to {settings.cfo_email}."
        except Exception:  # noqa: BLE001 - SMTP failure surfaced, not raised
            message = "Could not send — email transport (SMTP) unavailable."
        return templates.TemplateResponse(
            request, "partials/inline_toast.html", {"message": message}
        )

    @app.post("/cfo/investor/send", response_class=HTMLResponse)
    async def cfo_investor_send(
        request: Request, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        ctx = investor_update(db, today)
        channel = EmailChannel(
            SmtpTransport(host=settings.smtp_host, port=settings.smtp_port),
            sender=settings.email_sender,
        )
        try:
            await channel.send_investor_update(
                to=settings.cfo_email, ctx=ctx, company_name=settings.app_name
            )
            message = f"Investor update ({ctx['period']}) sent to {settings.cfo_email}."
        except Exception:  # noqa: BLE001 - SMTP/transport failure is surfaced, not raised
            message = "Could not send — email transport (SMTP) unavailable."
        return templates.TemplateResponse(
            request, "partials/inline_toast.html", {"message": message}
        )

    @app.post("/history/capture", response_class=HTMLResponse)
    async def history_capture(
        request: Request, db: Session = Depends(get_session)
    ) -> HTMLResponse:
        today = datetime.now(UTC).date()
        written = history_store.capture(db, registry, captured_at=today.isoformat(), as_of=today)
        db.commit()
        return templates.TemplateResponse(
            request,
            "partials/inline_toast.html",
            {"message": f"Snapshot captured — {written} metrics recorded for trends."},
        )

    @app.get("/parallel", response_class=HTMLResponse)
    async def parallel_page(request: Request, db: Session = Depends(get_session)) -> HTMLResponse:
        run = parallel.active_run(db)
        ctx: dict[str, Any] = {"run": run, "settings": settings, "nav_active": "parallel"}
        if run is not None:
            ctx["recs"] = parallel.reconcile(db, run)
            ctx["r"] = parallel.readiness(db, run)
        return templates.TemplateResponse(request, "parallel.html", ctx)

    @app.post("/parallel/start")
    async def parallel_start(
        name: str = Form("Cut-over parallel run"), db: Session = Depends(get_session)
    ) -> RedirectResponse:
        if parallel.active_run(db) is None:
            parallel.start_run(db, name=name, started_on=datetime.now(UTC).date(), days=30)
            db.commit()
        return RedirectResponse(url="/parallel", status_code=303)

    @app.post("/parallel/observe", response_class=HTMLResponse)
    async def parallel_observe(
        request: Request,
        domain: str = Form(...),
        metric: str = Form(...),
        external_value: float = Form(...),
        db: Session = Depends(get_session),
    ) -> HTMLResponse:
        run = parallel.active_run(db)
        if run is None:
            raise HTTPException(status_code=409, detail="no active parallel run")
        parallel.record_observation(
            db, run_id=run.id, observed_on=datetime.now(UTC).date(),
            domain=domain, metric=metric, external_value=external_value,
        )
        db.commit()
        return templates.TemplateResponse(
            request, "partials/recon.html", {"recs": parallel.reconcile(db, run)}
        )

    @app.get("/audit", response_class=HTMLResponse)
    async def audit_page(request: Request, db: Session = Depends(get_session)) -> HTMLResponse:
        entries = load_chain(db)
        return templates.TemplateResponse(
            request,
            "audit.html",
            {
                "entries": list(reversed(entries)),  # newest first for reading
                "chain_intact": verify_chain(entries),
                "traces": trace_store.recent(db),
                "settings": settings,
                "nav_active": "audit",
            },
        )

    return app


app = create_app()
