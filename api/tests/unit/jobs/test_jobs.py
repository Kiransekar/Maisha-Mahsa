"""The scheduled job functions, with injected session / fake Mahsa / in-memory email."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.email.channel import EmailChannel
from app.core.email.transport import InMemoryTransport
from app.core.mahsa_client import FoldResult, ResponseShape, Validation
from app.domains import build_registry
from app.jobs import run_brief, run_capture


class _GreenMahsa:
    async def fold(
        self,
        snapshot: dict[str, Any],
        *,
        domain=None,
        query=None,
        rules_version=None,
        recompute_claims=None,
    ) -> FoldResult:
        return FoldResult(
            global_intent=[0.0],
            global_dims=["x"],
            validation=Validation(status="green"),
            shape=ResponseShape(
                status="green",
                color="green",
                layout="default",
                requires_approval=False,
                global_score=90.0,
            ),
            rules_version="rv",
        )


def test_capture_job_records_metrics(session: Session) -> None:
    res = run_capture(session, build_registry(), captured_at="2026-06-24", as_of=date(2026, 6, 24))
    assert res["job"] == "capture"
    assert res["metrics"] > 0


@pytest.mark.asyncio
async def test_brief_job_dispatches_via_transport(session: Session) -> None:
    transport = InMemoryTransport()
    channel = EmailChannel(transport, sender="cfo@maisha.local")
    res = await run_brief(
        session,
        _GreenMahsa(),
        build_registry(),
        channel,  # type: ignore[arg-type]
        to="founder@maisha.local",
        company_name="Maisha-Mahsa",
        as_of=date(2026, 6, 24),
    )
    assert res["job"] == "brief"
    assert res["overall_score"] == 90.0  # all domains green
    assert len(transport.sent) == 1
    assert transport.sent[0].to == "founder@maisha.local"
