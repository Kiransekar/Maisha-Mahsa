"""Forecast eval cases. With nothing projected the snapshot reports a healthy baseline
(min cash 0, sentinel runway 999). Ground truth mirrors
``tests/unit/forecast/test_forecast_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_none(session: Session) -> None:
    # No forecast recorded — exercises the healthy-baseline branch of build_snapshot.
    pass


CASES: list[EvalCase] = [
    EvalCase(
        id="forecast-no-projection-baseline",
        domain="forecast",
        query="What's our projected minimum cash?",
        seed=_seed_none,
        as_of=_AS_OF,
        expect=Expectation(
            claims={
                "forecast_min_cash_paise": "0",
                "forecast_runway_months": "999",  # sentinel: no projection on record
            },
        ),
        stub_claim=ActionClaim(
            domain="forecast",
            narrative="No cash-flow projection is on record, so there is no min-cash risk yet.",
            claims={"forecast_min_cash_paise": "0", "forecast_runway_months": "999"},
        ),
    ),
]
