"""P2 eval-gated routing: route each domain to the local model only where it is perfect on the
golden eval, else to the cloud fallback; RoutedGenerator dispatches accordingly."""

from __future__ import annotations

from typing import Any

import pytest

from app.llm.routing import DomainScore, RoutedGenerator, decide_routes
from app.llm.schema import ActionClaim


def test_decide_routes_keeps_local_only_when_perfect() -> None:
    scores = [
        DomainScore("treasury", "ollama", 1.0),  # perfect -> stays local
        DomainScore("gst", "ollama", 0.8),  # imperfect -> cloud
        DomainScore("payroll", "claude", 1.0),  # only a cloud score -> cloud (no local score)
    ]
    routes = decide_routes(scores, primary="ollama", fallback="claude", threshold=1.0)
    assert routes == {"treasury": "ollama", "gst": "claude", "payroll": "claude"}


def test_decide_routes_threshold_is_tunable() -> None:
    scores = [DomainScore("gst", "ollama", 0.9)]
    assert decide_routes(scores, threshold=0.85)["gst"] == "ollama"
    assert decide_routes(scores, threshold=0.95)["gst"] == "claude"


class _TagProducer:
    """Returns a claim tagging which provider served it (via narrative)."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def produce(
        self, *, snapshot: dict[str, Any], query: str, domain: str, case_id: str = "",
        feedback: str | None = None,
    ) -> ActionClaim:
        return ActionClaim(domain=domain, narrative=self.tag)


@pytest.mark.asyncio
async def test_routed_generator_dispatches_by_domain() -> None:
    gen = RoutedGenerator(
        {"ollama": _TagProducer("local"), "claude": _TagProducer("cloud")},
        routes={"treasury": "ollama", "gst": "claude"},
        default="ollama",
    )
    treasury = await gen.produce(snapshot={}, query="?", domain="treasury")
    gst = await gen.produce(snapshot={}, query="?", domain="gst")
    unrouted = await gen.produce(snapshot={}, query="?", domain="vault")  # -> default
    assert treasury.narrative == "local"
    assert gst.narrative == "cloud"
    assert unrouted.narrative == "local"


def test_routed_generator_requires_default_producer() -> None:
    with pytest.raises(ValueError):
        RoutedGenerator({"claude": _TagProducer("cloud")}, routes={}, default="ollama")
