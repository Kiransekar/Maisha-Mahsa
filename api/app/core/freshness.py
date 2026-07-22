"""WS7.7 — data-staleness assembler (UX research T4).

Pure: session + ``as_of`` + an injected threshold map in, plain dicts out. **No clock inside**
(CLAUDE.md §2 determinism) — the route supplies ``as_of``, so the same DB on the same date always
reports the same freshness.

The rule this file exists to enforce (mirrors the Rust WS3.3 absent-signal rule, and WS7 contract
T4): **absent signal is unknown, never healthy.** A source with no rows reports ``never synced``
with ``last_updated: None`` — never a fabricated recent date, and never ``healthy``. A figure
recomputed against stale inputs is worse than no figure at all, so staleness must be loud.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.gst import GstReturn
from app.db.models.payroll import PayrollRun
from app.db.models.treasury import BankAccount, BankTransaction
from app.db.models.vault import Document

# Max acceptable age in days per source, before the source reads stale. Injected into
# ``build_freshness`` so tests (and any future per-company policy) can override it; these are the
# defaults for the cadence each source actually has.
DEFAULT_THRESHOLD_DAYS: dict[str, int] = {
    "bank_feeds": 2,  # feeds sync daily; two days is already a reconciliation problem
    "gst_filings": 45,  # monthly returns + a filing window
    "payroll": 45,  # monthly run + a filing window
    "documents": 120,  # uploads are event-driven, not periodic
}

_NEVER = "Never synced — this source has no data at all. Nothing here is backed by it."


@dataclass(frozen=True)
class SourceFreshness:
    key: str
    label: str
    last_updated: str | None  # ISO date; None == never synced
    age_days: int | None  # None == never synced
    threshold_days: int
    stale: bool
    synced: bool
    note: str


def _iso_date(raw: str | None) -> date | None:
    """Parse a stored date/datetime string to a date. Unparseable or empty == unknown, never a
    guess — the caller then treats it as never-synced rather than inventing a date."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _latest(session: Session, column: Any) -> date | None:
    """Newest parseable date in ``column``. NULL/garbage rows simply do not contribute.

    ponytail: DISTINCT then parse in Python rather than SQL ``MAX`` — a garbage string sorts
    lexically above a real ISO date and would mask it. Bounded by distinct dates (one per day).
    """
    raws = session.scalars(select(column).where(column.is_not(None)).distinct()).all()
    parsed = [d for d in (_iso_date(r) for r in raws) if d is not None]
    return max(parsed) if parsed else None


def _source(
    key: str, label: str, last: date | None, as_of: date, threshold_days: int
) -> SourceFreshness:
    if last is None:
        return SourceFreshness(
            key=key,
            label=label,
            last_updated=None,
            age_days=None,
            threshold_days=threshold_days,
            stale=True,  # unknown is never healthy
            synced=False,
            note=_NEVER,
        )
    # A future timestamp yields a negative age; we report it as-is rather than clamping, because
    # silently normalising bad data is exactly the drift this module exists to surface.
    age = (as_of - last).days
    stale = age > threshold_days
    note = (
        f"Last updated {last.isoformat()} — {age} day(s) old, past the {threshold_days}-day "
        "limit. Figures computed from this source are not current."
        if stale
        else f"Last updated {last.isoformat()} — {age} day(s) old."
    )
    return SourceFreshness(
        key=key,
        label=label,
        last_updated=last.isoformat(),
        age_days=age,
        threshold_days=threshold_days,
        stale=stale,
        synced=True,
        note=note,
    )


def _bank_last(session: Session) -> date | None:
    """Bank feeds: the newest explicit ``last_sync`` on any account, else the newest transaction
    date. A configured account that has never synced does NOT count as a sync."""
    return _latest(session, BankAccount.last_sync) or _latest(session, BankTransaction.txn_date)


def _collect(session: Session, as_of: date, thresholds: dict[str, int]) -> list[SourceFreshness]:
    latest: dict[str, tuple[str, date | None]] = {
        "bank_feeds": ("Bank feeds", _bank_last(session)),
        "gst_filings": ("GST filings", _latest(session, GstReturn.filed_date)),
        "payroll": ("Payroll runs", _latest(session, PayrollRun.run_date)),
        "documents": ("Uploaded documents", _latest(session, Document.upload_date)),
    }
    return [
        _source(key, label, last, as_of, thresholds.get(key, DEFAULT_THRESHOLD_DAYS[key]))
        for key, (label, last) in latest.items()
    ]


def build_freshness(
    session: Session, as_of: date, thresholds: dict[str, int] | None = None
) -> dict[str, Any]:
    """Per-source freshness plus the worst case across all of them.

    ``overall.status`` is ``fresh`` only when every source is synced and inside its threshold.
    Anything else — one stale feed, one never-synced source — degrades the whole report, because
    the Owner needs to know the figures on screen may be built on old inputs.
    """
    sources = _collect(session, as_of, thresholds or {})
    never = [s.key for s in sources if not s.synced]
    stale = [s.key for s in sources if s.stale and s.synced]
    known_ages = [s.age_days for s in sources if s.age_days is not None]

    if never:
        status = "unknown"
        headline = f"{len(never)} data source(s) have never synced."
    elif stale:
        status = "stale"
        headline = f"{len(stale)} data source(s) are past their freshness limit."
    else:
        status = "fresh"
        headline = "All data sources are inside their freshness limits."

    return {
        "as_of": as_of.isoformat(),
        "sources": [asdict(s) for s in sources],
        "overall": {
            "status": status,
            "healthy": status == "fresh",
            "headline": headline,
            # Worst KNOWN age. None means no source has ever synced — not "0 days old".
            "worst_age_days": max(known_ages) if known_ages else None,
            "never_synced": never,
            "stale": stale,
        },
    }
