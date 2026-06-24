"""Snapshot history for trend charts. ``capture`` writes one row per scalar fact per domain at
a point in time; ``domain_series`` reads them back chronologically. This is observability data
(plotting only) — it never feeds money math, so floats are acceptable here. Charts only render
metrics with ≥2 real points; nothing is fabricated."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.core.router import DomainRouter
from app.db.models.shared import MetricSnapshot
from app.llm.tools import enrich


def _build_snapshot(service: BaseDomainService, session: Session, as_of: date | None) -> dict:
    try:
        return service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        return service.build_snapshot(session)


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def capture(
    session: Session, registry: DomainRouter, *, captured_at: str, as_of: date | None = None
) -> int:
    """Capture every domain's current numeric facts. Returns the number of rows written."""
    written = 0
    for domain in registry.domains():
        service = registry.get(domain)
        if service is None:
            continue
        facts = enrich(_build_snapshot(service, session, as_of))
        for key, raw in facts.items():
            if key == "as_of":
                continue
            num = _numeric(raw)
            if num is None:
                continue
            session.add(
                MetricSnapshot(captured_at=captured_at, domain=domain, metric=key, value=num)
            )
            written += 1
    session.flush()
    return written


def domain_series(session: Session, domain: str) -> dict[str, list[tuple[str, float]]]:
    """All captured series for a domain: ``{metric: [(captured_at, value), …]}`` chronological."""
    rows = session.scalars(
        select(MetricSnapshot)
        .where(MetricSnapshot.domain == domain)
        .order_by(MetricSnapshot.id.asc())
    ).all()
    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        out.setdefault(r.metric, []).append((r.captured_at, r.value))
    return out
