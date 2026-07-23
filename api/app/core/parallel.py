"""Layer 6 — the parallel run. Maisha runs alongside the founder's existing process for a
period; each day the founder records what their current system says (a
:class:`ParallelObservation`) and we reconcile it against Maisha's captured metric of the same
``(domain, metric)``. A run is cut-over-ready only when every comparison agrees within tolerance
across enough days — a deterministic go/no-go gate, no hand-waving."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.shared import MetricSnapshot, ParallelObservation, ParallelRun


def start_run(session: Session, *, name: str, started_on: date, days: int = 30) -> ParallelRun:
    run = ParallelRun(
        name=name,
        started_on=started_on.isoformat(),
        ends_on=(started_on + timedelta(days=days)).isoformat(),
        status="active",
    )
    session.add(run)
    session.flush()
    return run


def active_run(session: Session) -> ParallelRun | None:
    return session.scalars(
        select(ParallelRun).where(ParallelRun.status == "active").order_by(ParallelRun.id.desc())
    ).first()


def close_run(session: Session, run: ParallelRun) -> None:
    run.status = "closed"
    session.flush()


def record_observation(
    session: Session,
    *,
    run_id: int,
    observed_on: date,
    domain: str,
    metric: str,
    external_value: float,
) -> ParallelObservation:
    obs = ParallelObservation(
        run_id=run_id,
        observed_on=observed_on.isoformat(),
        domain=domain,
        metric=metric,
        external_value=external_value,
    )
    session.add(obs)
    session.flush()
    return obs


def _maisha_value(session: Session, domain: str, metric: str, on_or_before: str) -> float | None:
    """Maisha's captured value for a metric, as of (or before) a date."""
    return session.scalars(
        select(MetricSnapshot.value)
        .where(
            MetricSnapshot.domain == domain,
            MetricSnapshot.metric == metric,
            MetricSnapshot.captured_at <= on_or_before,
        )
        .order_by(MetricSnapshot.captured_at.desc(), MetricSnapshot.id.desc())
        .limit(1)
    ).first()


@dataclass(frozen=True)
class Recon:
    observed_on: str
    domain: str
    metric: str
    external: float
    maisha: float | None  # None when Maisha has no captured value to compare
    variance: float | None
    ok: bool  # reconciled and within tolerance


def reconcile(session: Session, run: ParallelRun, *, tolerance: float = 0.0) -> list[Recon]:
    rows = session.scalars(
        select(ParallelObservation)
        .where(ParallelObservation.run_id == run.id)
        .order_by(ParallelObservation.observed_on.asc(), ParallelObservation.id.asc())
    ).all()
    out: list[Recon] = []
    for o in rows:
        maisha = _maisha_value(session, o.domain, o.metric, o.observed_on)
        variance = None if maisha is None else round(o.external_value - maisha, 6)
        ok = maisha is not None and abs(variance) <= tolerance  # type: ignore[arg-type]
        out.append(Recon(o.observed_on, o.domain, o.metric, o.external_value, maisha, variance, ok))
    return out


@dataclass
class Readiness:
    comparisons: int
    matches: int
    mismatches: int
    agreement_pct: float
    distinct_days: int
    recommendation: str  # "GO" | "HOLD"
    discrepancies: list[Recon] = field(default_factory=list)


def readiness(
    session: Session, run: ParallelRun, *, tolerance: float = 0.0, min_days: int = 30
) -> Readiness:
    recs = reconcile(session, run, tolerance=tolerance)
    matches = sum(1 for r in recs if r.ok)
    mismatches = len(recs) - matches
    distinct_days = len({r.observed_on for r in recs})
    pct = round(100.0 * matches / len(recs), 1) if recs else 0.0
    # Cut-over ready only when everything agrees across at least min_days of observations.
    go = bool(recs) and mismatches == 0 and distinct_days >= min_days
    return Readiness(
        comparisons=len(recs),
        matches=matches,
        mismatches=mismatches,
        agreement_pct=pct,
        distinct_days=distinct_days,
        recommendation="GO" if go else "HOLD",
        discrepancies=[r for r in recs if not r.ok],
    )
