"""Snapshot history + sparkline charts: real captured points only, no fabrication."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core import history_store
from app.domains import build_registry
from app.web.charts import sparkline


def test_sparkline_needs_two_points() -> None:
    assert sparkline([]) == ""
    assert sparkline([5.0]) == ""  # a single point is not a trend
    svg = sparkline([1.0, 2.0, 3.0])
    assert svg.startswith("<svg") and "<polyline" in svg
    assert svg.count(",") >= 3  # 3 plotted points -> at least 3 coordinate pairs


def test_sparkline_flat_series_is_safe() -> None:
    svg = sparkline([4.0, 4.0, 4.0])  # span 0 must not divide-by-zero
    assert "<polyline" in svg


def test_capture_then_series(session: Session) -> None:
    registry = build_registry()
    n1 = history_store.capture(session, registry, captured_at="2026-06-23", as_of=date(2026, 6, 23))
    n2 = history_store.capture(session, registry, captured_at="2026-06-24", as_of=date(2026, 6, 24))
    assert n1 > 0 and n2 > 0  # numeric facts captured for every domain

    series = history_store.domain_series(session, "gst")
    assert series  # gst has metrics
    # every captured metric now has two chronological points
    for points in series.values():
        assert [p[0] for p in points] == ["2026-06-23", "2026-06-24"]
        assert all(isinstance(v, float) for _, v in points)


def test_domain_series_empty_when_no_capture(session: Session) -> None:
    assert history_store.domain_series(session, "treasury") == {}
