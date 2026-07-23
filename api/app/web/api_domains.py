"""WS7.4 — JSON API for the five hubs + the CA Audit Room (the CA landing, §WS5.3).

Deliberately thin, same shape as ``api_router.py``/``api_approvals.py``: it reuses the existing
pure assemblers/services rather than re-deriving anything —

  * ``app.core.cfo.collect_health``      — live Mahsa-scored domain health
  * ``app.core.overview.collect_kpis``   / ``upcoming_deadlines`` — the KPI strip + calendar
  * ``app.core.mahsa_coverage.badge_state`` — the ONE honesty gate for every figure (§0.4): a
    figure is ``verified`` only when its raw fact key is a Mahsa-recomputed coverage target;
    anything else is ``honest_pending`` — never a hardcoded ``verified`` (same rule ``app.core.
    ask`` already applies to Ask Maisha figures).
  * ``app.web.actions.actions_for``      — the mutations available on a domain page
  * ``app.core.audit`` / ``audit_store`` — the hash-chained log + its truthful verification

Mahsa unreachable is STATED (``mahsa_up: false`` + message), never silently absorbed into a
thinner payload, and no domain health is ever shown without a live recompute.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import ca_seat, ca_threads, history_store
from app.core.ask import answer_query
from app.core.audit import verify_chain
from app.core.audit_pack import build_audit_pack, pack_to_csv_zip
from app.core.audit_store import load_chain
from app.core.cfo import DomainHealth, collect_health
from app.core.entitlement_deps import SessionContext, get_session_context
from app.core.landing import mask_figures
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.mahsa_coverage import badge_state
from app.core.overview import collect_kpis, upcoming_deadlines
from app.core.pdf import audit_pack_pdf
from app.core.principal import Principal
from app.core.rbac import Capability, Role, can
from app.core.rbac_deps import require, resolve_principal
from app.core.verify import FigureVerdict
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.llm.tools import enrich
from app.web.actions import Field as ActionField
from app.web.actions import actions_for
from app.web.exceptions_router import _snapshot
from app.web.format import fmt_value, humanize

# WS5.1: `read` baseline on every route; the Audit Room additionally needs `view_audit`.
router = APIRouter(
    prefix="/api", tags=["domains"], dependencies=[Depends(require(Capability.READ))]
)

_registry = build_registry()

MAHSA_DOWN = (
    "Mahsa is unreachable, so domain health is not being independently scored right now. "
    "No score shown here has been fabricated."
)


def _today() -> date:
    return datetime.now(UTC).date()


def _figure(key: str, value: Any) -> dict[str, Any]:
    """One snapshot figure with its honest coverage badge — never hardcoded verified."""
    return {
        "key": key,
        "label": humanize(key),
        "value": fmt_value(key, value),
        "raw": value,
        "state": badge_state(key),
    }


def _figures_for(session: Session, domain: str, role: Role) -> list[dict[str, Any]]:
    """Every figure list this module (and api_actions' after_figures) serializes leaves through
    T11's ``mask_figures`` — ``role`` is a required positional so a call site that forgets it is
    a loud TypeError, never a silently unmasked payload."""
    service = _registry.get(domain)
    if service is None:
        return []
    snapshot = _snapshot(service, session, _today())
    facts = enrich(snapshot)
    return mask_figures(role, [_figure(k, v) for k, v in sorted(facts.items()) if k != "as_of"])


def _field_json(f: ActionField) -> dict[str, Any]:
    """One action Field for the SPA — recursive so ``lines`` fields ship their column
    sub-schema (P0-3 entry forms)."""
    out: dict[str, Any] = {
        "name": f.name,
        "label": f.label,
        "type": f.type,
        "required": f.required,
        "placeholder": f.placeholder,
        "options": list(f.options),
    }
    if f.columns:
        out["columns"] = [_field_json(c) for c in f.columns]
    return out


def _health_row(domain: str, h: DomainHealth | None) -> dict[str, Any]:
    return {
        "key": domain,
        "score": h.score if h else None,
        "status": h.status if h else None,
        "color": h.color if h else None,
        "requires_approval": h.requires_approval if h else False,
    }


@router.get("/domains")
async def domains_json(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """The five-hub overview: every domain's live health + honest coverage + the shared
    KPI strip and compliance calendar (direct DB reads, so they render even if Mahsa is down)."""
    as_of = _today()
    health_by_domain: dict[str, DomainHealth] = {}
    mahsa_up = True
    try:
        for h in await collect_health(db, mahsa, _registry, as_of=as_of):
            health_by_domain[h.domain] = h
    except MahsaError:
        mahsa_up = False

    domains = []
    for d in _registry.domains():
        figures = _figures_for(db, d, principal.role)
        # a T11-masked figure has no "state" — it counts in total, never as verified
        verified = sum(1 for f in figures if f.get("state") == "verified")
        domains.append(
            {
                **_health_row(d, health_by_domain.get(d)),
                "coverage": {"verified": verified, "total": len(figures)},
            }
        )

    return {
        "as_of": as_of.isoformat(),
        "mahsa_up": mahsa_up,
        "mahsa_down_message": None if mahsa_up else MAHSA_DOWN,
        "domains": domains,
        "kpis": collect_kpis(db, as_of),
        "deadlines": upcoming_deadlines(db, as_of),
    }


@router.get("/domains/{domain}")
async def domain_json(
    domain: str,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """One domain's snapshot figures (each badged), its deadlines, and its available actions."""
    service = _registry.get(domain)
    if service is None:
        raise HTTPException(status_code=404, detail=f"unknown domain '{domain}'")
    as_of = _today()

    health = None
    mahsa_up = True
    try:
        snapshot = _snapshot(service, db, as_of)
        fold = await mahsa.fold(snapshot, domain=domain)
        shape = fold.shape
        score = shape.domain_score if shape.domain_score is not None else shape.global_score
        health = {
            "status": fold.validation.status,
            "score": round(score, 1) if score is not None else None,
            "requires_approval": shape.requires_approval,
        }
    except MahsaError:
        mahsa_up = False

    actions = [
        {
            "key": a.key,
            "label": a.label,
            "fields": [_field_json(f) for f in a.fields],
        }
        for a in actions_for(domain)
    ]

    return {
        "domain": domain,
        "as_of": as_of.isoformat(),
        "mahsa_up": mahsa_up,
        "mahsa_down_message": None if mahsa_up else MAHSA_DOWN,
        "health": health,
        "figures": _figures_for(db, domain, principal.role),
        "deadlines": [e for e in upcoming_deadlines(db, as_of) if e.get("domain") == domain],
        "actions": actions,
    }


@router.get("/domains/{domain}/history")
async def domain_history_json(
    domain: str,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """P2-3: trend series for the SPA sparklines — the SAME query the HTMX /domains page's
    sparklines already read (``history_store.domain_series``), so the two surfaces can never
    disagree on what was actually captured. Honest >=2-point rule: a metric with fewer than two
    real captures is omitted entirely — never a fabricated flat line."""
    _known_domain(domain)
    series = history_store.domain_series(db, domain)
    return {
        "domain": domain,
        "series": {
            metric: [{"captured_at": t, "value": v} for t, v in points]
            for metric, points in series.items()
            if len(points) >= 2
        },
    }


# --- P1-1 Ask Maisha (SPA twin of the HTMX /ask page) ----------------------------------------


class AskBody(BaseModel):
    q: str = Field(min_length=1)


def _tri_state(verdict: FigureVerdict) -> str:
    """Project a figure's FigureVerdict (the SAME object app.core.ask threads per figure) to
    the SPA's tri-state string. Fail CLOSED (§0.4): only an explicit ``verified`` renders ✓;
    ``honest_pending`` renders ◐; anything else — blocked, or a future state — is unbacked."""
    if verdict.verified:
        return "verified"
    if verdict.honest_pending:
        return "honest_pending"
    return "unbacked"


@router.post("/ask")
async def ask_json(
    body: AskBody,
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
) -> dict[str, Any]:
    """The Ask.tsx backend: the SAME ``app.core.ask.answer_query`` pipeline the HTMX /ask page
    calls, verbatim — no forked logic, so a figure's verdict can never drift between the two
    surfaces. This wrapper only projects the Answer view-model to JSON."""
    answer = await answer_query(
        db,
        query=body.q,
        registry=_registry,
        settings=get_settings(),
        as_of=_today(),
        mahsa=mahsa,
    )
    return {
        "query": answer.query,
        "domain": answer.domain,
        "narrative": answer.narrative,
        "figures": [
            {"label": f.label, "value": f.value, "state": _tri_state(f.verdict)}
            for f in answer.figures
        ],
        "citations": [
            {"rule_id": c.rule_id, "text": c.text, "citation": c.citation, "domain": c.domain}
            for c in answer.citations
        ],
        "status": answer.status,
        "requires_approval": answer.requires_approval,
        "abstained": answer.abstained,
        "mahsa_up": answer.mahsa_up,
        "provenance": answer.provenance,
    }


@router.get("/audit", dependencies=[Depends(require(Capability.VIEW_AUDIT))])
async def audit_json(
    db: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """The CA Audit Room: the hash-chained log, newest first, with a TRUTHFUL chain-verification
    result — a broken chain is reported as broken, never silently repaired or hidden."""
    sealed = load_chain(db)  # oldest -> newest, the order the chain actually verifies in
    intact = verify_chain(sealed)
    newest_first = list(reversed(sealed))
    page = newest_first[offset : offset + limit]
    return {
        "chain_intact": intact,
        "total": len(sealed),
        "limit": limit,
        "offset": offset,
        "entries": [
            {
                "timestamp": e.timestamp,
                "action": e.action,
                "domain": e.domain,
                "user_id": e.user_id,
                "query": e.query,
                "validation_status": e.validation_status,
                "rules_version": e.rules_version,
                "prev_hash": e.prev_hash,
                "this_hash": e.this_hash,
            }
            for e in page
        ],
    }


# --- WS8.2 CA query threads ------------------------------------------------------------------
# raise/read/resolve are Audit-Room actions -> view_audit (CA holds it; Investor does not).
# respond-with-doc is a books-side answer -> write (Accountant/Owner/Admin; CA excluded by
# construction — a CA can never answer, let alone mutate, its own query).


class ThreadRaise(BaseModel):
    domain: str
    entry_ref: str = Field(min_length=1)
    question: str = Field(min_length=1)


class ThreadRespond(BaseModel):
    doc_id: str = Field(min_length=1)  # vault documents.id — the evidence link
    note: str = ""


class ThreadResolve(BaseModel):
    note: str = ""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _thread_json(session: Session, thread: Any) -> dict[str, Any]:
    return {
        "id": thread.id,
        "created_at": thread.created_at,
        "domain": thread.domain,
        "entry_ref": thread.entry_ref,
        "question": thread.question,
        "state": thread.state,
        "raised_by": thread.raised_by,
        "events": [
            {
                "timestamp": ev.timestamp,
                "event": ev.event,
                "user_id": ev.user_id,
                "note": ev.note,
                "doc_id": ev.doc_id,
                "audit_hash": ev.audit_hash,
            }
            for ev in ca_threads.events_for(session, thread.id)
        ],
    }


def _known_domain(domain: str) -> str:
    if _registry.get(domain) is None:
        raise HTTPException(status_code=404, detail=f"unknown domain '{domain}'")
    return domain


@router.get("/audit/threads")
async def threads_json(
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.VIEW_AUDIT)),
) -> dict[str, Any]:
    """All CA query threads, newest first, each with its full sealed event history — plus the
    caller's OWN action capabilities, so the SPA renders enabled/disabled-with-reason from the
    server's verdict, never from a client-side role guess (same `can_confirm` convention as
    api_payroll/api_filings)."""
    can_respond = can(principal.role, Capability.WRITE)
    return {
        "threads": [_thread_json(db, t) for t in ca_threads.list_threads(db)],
        "can_respond": can_respond,
        "respond_denied_reason": None if can_respond else (
            "missing capability: write — responding attaches books-side evidence; "
            "an Accountant or the Owner answers this query"
        ),
        "can_export": can(principal.role, Capability.EXPORT),
    }


@router.get("/audit/threads/{thread_id}", dependencies=[Depends(require(Capability.VIEW_AUDIT))])
async def thread_json(thread_id: int, db: Session = Depends(get_session)) -> dict[str, Any]:
    thread = db.get(ca_threads.CaThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"unknown thread {thread_id}")
    return _thread_json(db, thread)


@router.post("/audit/threads")
async def thread_raise(
    body: ThreadRaise,
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.VIEW_AUDIT)),
) -> dict[str, Any]:
    """Raise a query pinned to an entry. The raise event is sealed onto the audit chain."""
    _known_domain(body.domain)
    thread = ca_threads.raise_thread(
        db,
        timestamp=_now_iso(),
        domain=body.domain,
        entry_ref=body.entry_ref,
        question=body.question,
        user_id=principal.user_id,
    )
    db.commit()
    return _thread_json(db, thread)


@router.post("/audit/threads/{thread_id}/respond")
async def thread_respond(
    thread_id: int,
    body: ThreadRespond,
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.WRITE)),
) -> dict[str, Any]:
    """Respond WITH a vault document (evidence link required, validated to exist)."""
    try:
        thread = ca_threads.respond_thread(
            db,
            thread_id=thread_id,
            timestamp=_now_iso(),
            note=body.note,
            doc_id=body.doc_id,
            user_id=principal.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _thread_json(db, thread)


@router.post("/audit/threads/{thread_id}/resolve")
async def thread_resolve(
    thread_id: int,
    body: ThreadResolve,
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.VIEW_AUDIT)),
) -> dict[str, Any]:
    """Close a responded query."""
    try:
        thread = ca_threads.resolve_thread(
            db, thread_id=thread_id, timestamp=_now_iso(), note=body.note,
            user_id=principal.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _thread_json(db, thread)


@router.get("/audit/sample", dependencies=[Depends(require(Capability.VIEW_AUDIT))])
async def audit_sample(
    date_from: str,
    date_to: str,
    n: int = Query(ge=1, le=200),
    domain: str | None = None,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Deterministic voucher sample (seeded by org + spec hash, NO RNG): same spec, same org,
    same sample — re-runnable by the CA in a dispute. Each voucher carries its vault doc
    bundle refs."""
    return ca_threads.sample_selection(
        db, org=principal.org_id, domain=domain, date_from=date_from, date_to=date_to, n=n
    )


# ---- WS8.3 CA seat onboarding: free + unlimited seat, invite → accept, referral events ------


class CaInvite(BaseModel):
    email: str = Field(min_length=3)


@router.post("/ca/invite")
async def ca_invite(
    body: CaInvite,
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.MANAGE_USERS)),
    ctx: SessionContext = Depends(get_session_context),
) -> dict[str, Any]:
    """Invite a CA by email (Owner/Admin). The seat is FREE + UNLIMITED — never counted
    against the plan's seat gate (entitlements.SEAT_EXEMPT_ROLES). Seals ``ca_invited``."""
    try:
        membership = ca_seat.invite_ca(
            db, principal=principal, email=body.email, plan=ctx.org_plan, timestamp=_now_iso()
        )
    except PermissionError as exc:  # defence in depth; require() above already gates
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {
        "membership_id": membership.id,
        "role": membership.role,
        "status": membership.status,
        "seat": "free_unlimited",
    }


@router.get("/ca/pending")
async def ca_pending(
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.MANAGE_USERS)),
) -> dict[str, Any]:
    """Pending CA invites for the caller's org (Owner/Admin — same gate as the invite itself,
    P1-3 settings surface)."""
    return {"invites": ca_seat.list_pending(db, org_id=principal.org_id)}


@router.post("/ca/accept")
async def ca_accept(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """The invited CA accepts their pending seat — matched on the VERIFIED token's email
    within the token's org (§0.8), never on request-supplied identity. Seals ``ca_joined``
    (+ ``ca_referred_org`` when this CA already serves another org)."""
    try:
        membership, referred = ca_seat.accept_ca(db, principal=principal, timestamp=_now_iso())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {
        "membership_id": membership.id,
        "status": membership.status,
        "referred_org": referred,
    }


# ---- WS8.1 remainder: the full Audit Pack + downloadable artifacts ---------------------------


def _audit_pack_entity_data(db: Session, *, org_id: str, rules_version: str) -> dict[str, Any]:
    """Assemble ``build_audit_pack``'s input from the EXISTING domain services — every figure
    below was already computed (and, where portable, Mahsa-claimed) by its own domain; nothing
    is recomputed here (§0.4)."""
    from sqlalchemy import select

    from app.db.models.gst import GstReturn
    from app.db.models.ledger import ChartOfAccounts
    from app.db.models.tax import TdsReturn
    from app.domains.ledger.service import LedgerService
    from app.domains.payables.service import PayablesService
    from app.domains.payroll.service import PayrollService

    # Concrete, stateless services (same instances-by-construction as build_registry uses) —
    # concrete types so the ledger/payables/payroll-specific methods are statically checked.
    ledger = LedgerService()
    payables = PayablesService()
    payroll = PayrollService()
    as_of = _today()

    accounts = db.scalars(select(ChartOfAccounts).order_by(ChartOfAccounts.code)).all()
    gl = [
        {"code": a.code, "name": a.name,
         "closing_balance": ledger.general_ledger(db, a.id)["closing_balance"]}
        for a in accounts
    ]
    payroll_metrics = payroll.build_snapshot(db, as_of)
    return {
        "org_id": org_id,
        "rules_version": rules_version,
        "trial_balance": ledger.trial_balance(db),
        "profit_and_loss": ledger.profit_and_loss(db),
        "balance_sheet": ledger.balance_sheet(db),
        "general_ledger": gl,
        "statutory_registers": {
            "tds_returns": [
                {"return_type": r.return_type, "quarter": r.quarter, "status": r.status,
                 "total_deducted": int(r.total_deducted),
                 "late_filing_fee": int(r.late_filing_fee)}
                for r in db.scalars(select(TdsReturn).order_by(TdsReturn.quarter)).all()
            ],
            "gst_returns": [
                {"return_type": r.return_type, "filing_period": r.filing_period,
                 "status": r.status, "tax_payable": int(r.tax_payable),
                 "late_fee": int(r.late_fee), "interest": int(r.interest)}
                for r in db.scalars(select(GstReturn).order_by(GstReturn.filing_period)).all()
            ],
            "payroll": {
                "monthly_burn": int(payroll_metrics["monthly_burn"]),
                "lwf_due_paise": int(payroll_metrics["metrics"]["lwf_due_paise"]),
                "monthly_bonus_required_paise": int(
                    payroll_metrics["metrics"]["monthly_bonus_required_paise"]
                ),
            },
        },
        # No Form 26AS statement store exists yet — the section states that honestly (never a
        # vacuous "reconciled" from two empty lists). When a 26AS upload lands, feed
        # tax_calc.reconcile_26as output here.
        "form_26as_reconciliation": None,
        "msme_ageing": {
            "ap_aging": payables.ap_aging(db, as_of),
            "msme_max_days_unpaid": payables.msme_max_days_unpaid(db, as_of),
        },
    }


async def _build_pack(db: Session, mahsa: MahsaClient, principal: Principal) -> dict[str, Any]:
    """Rules version comes from the LIVE Mahsa engine (its /health), the org from the session
    principal (§0.8). Mahsa unreachable → 503, stated — never a fabricated version string."""
    try:
        health = await mahsa.health()
    except MahsaError:
        raise HTTPException(
            status_code=503,
            detail="Mahsa is unreachable, so the audit pack cannot bind a rules version. "
                   "No pack was generated and nothing was fabricated.",
        ) from None
    entity_data = _audit_pack_entity_data(
        db, org_id=principal.org_id, rules_version=health["rules_version"]
    )
    return build_audit_pack(entity_data)


@router.get("/audit/pack")
async def audit_pack_json(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(require(Capability.VIEW_AUDIT)),
) -> dict[str, Any]:
    """The full §WS8.1 Audit Pack (TB/P&L/BS/GL/registers/26AS/MSME), every figure badged via
    the one §0.4 gate, sealed with its integrity hash."""
    return await _build_pack(db, mahsa, principal)


@router.get("/audit/pack.zip")
async def audit_pack_zip(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(require(Capability.EXPORT)),
) -> Response:
    pack = await _build_pack(db, mahsa, principal)
    return Response(
        content=pack_to_csv_zip(pack),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="audit_pack.zip"'},
    )


@router.get("/audit/pack.pdf")
async def audit_pack_pdf_route(
    db: Session = Depends(get_session),
    mahsa: MahsaClient = Depends(get_mahsa),
    principal: Principal = Depends(require(Capability.EXPORT)),
) -> Response:
    pack = await _build_pack(db, mahsa, principal)
    return Response(
        content=audit_pack_pdf(pack),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="audit_pack.pdf"'},
    )
