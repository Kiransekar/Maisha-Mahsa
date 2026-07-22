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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.audit import verify_chain
from app.core.audit_store import load_chain
from app.core.cfo import DomainHealth, collect_health
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.mahsa_coverage import badge_state
from app.core.overview import collect_kpis, upcoming_deadlines
from app.db.session import get_session
from app.deps import get_mahsa
from app.domains import build_registry
from app.llm.tools import enrich
from app.web.actions import actions_for
from app.web.exceptions_router import _snapshot
from app.web.format import fmt_value, humanize

router = APIRouter(prefix="/api", tags=["domains"])

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


def _figures_for(session: Session, domain: str) -> list[dict[str, Any]]:
    service = _registry.get(domain)
    if service is None:
        return []
    snapshot = _snapshot(service, session, _today())
    facts = enrich(snapshot)
    return [_figure(k, v) for k, v in sorted(facts.items()) if k != "as_of"]


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
        figures = _figures_for(db, d)
        verified = sum(1 for f in figures if f["state"] == "verified")
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
            "fields": [
                {
                    "name": f.name,
                    "label": f.label,
                    "type": f.type,
                    "required": f.required,
                    "placeholder": f.placeholder,
                    "options": list(f.options),
                }
                for f in a.fields
            ],
        }
        for a in actions_for(domain)
    ]

    return {
        "domain": domain,
        "as_of": as_of.isoformat(),
        "mahsa_up": mahsa_up,
        "mahsa_down_message": None if mahsa_up else MAHSA_DOWN,
        "health": health,
        "figures": _figures_for(db, domain),
        "deadlines": [e for e in upcoming_deadlines(db, as_of) if e.get("domain") == domain],
        "actions": actions,
    }


@router.get("/audit")
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
