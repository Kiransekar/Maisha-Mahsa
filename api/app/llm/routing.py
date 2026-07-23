"""Eval-gated model routing (P2). Pick the provider per *domain* from measured eval quality:
keep the cheap local model where it is good enough, fall back to the stronger cloud model only
where it isn't. For a zero-error finance product the bar is deliberately strict — the default
threshold is 1.0, i.e. the local model must be **perfect** on a domain's golden cases to serve
it; otherwise that domain routes to the fallback.

``decide_routes`` is pure (feed it scores from a real ``make eval-real`` run). ``RoutedGenerator``
is a :class:`ClaimProducer` that dispatches each draft to the chosen provider's generator.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.llm.maisha import ClaimProducer
from app.llm.schema import ActionClaim


@dataclass(frozen=True)
class DomainScore:
    domain: str
    provider: str
    pass_rate: float  # 0.0..1.0 from the golden eval (fraction of the domain's cases passed)


def decide_routes(
    scores: list[DomainScore],
    *,
    primary: str = "ollama",
    fallback: str = "claude",
    threshold: float = 1.0,
) -> dict[str, str]:
    """Map each domain to a provider: ``primary`` if its measured pass rate ≥ ``threshold``,
    else ``fallback``. Domains with no ``primary`` score route to ``fallback`` (fail safe)."""
    primary_rate: dict[str, float] = defaultdict(float)
    for s in scores:
        if s.provider == primary:
            primary_rate[s.domain] = max(primary_rate[s.domain], s.pass_rate)
    domains = {s.domain for s in scores}
    return {
        d: (primary if primary_rate.get(d, 0.0) >= threshold else fallback) for d in sorted(domains)
    }


class RoutedGenerator:
    """Dispatches each draft to the provider chosen for its domain (``routes``), falling back to
    ``default`` for unrouted domains. Satisfies :class:`ClaimProducer`."""

    label = "routed"

    def __init__(
        self,
        producers: dict[str, ClaimProducer],
        routes: dict[str, str],
        *,
        default: str = "ollama",
    ) -> None:
        if default not in producers:
            raise ValueError(f"default provider {default!r} has no producer")
        self._producers = producers
        self._routes = routes
        self._default = default

    def provider_for(self, domain: str) -> str:
        provider = self._routes.get(domain, self._default)
        return provider if provider in self._producers else self._default

    async def produce(
        self,
        *,
        snapshot: dict[str, Any],
        query: str,
        domain: str,
        case_id: str = "",
        feedback: str | None = None,
        memory: str | None = None,
    ) -> ActionClaim:
        producer = self._producers[self.provider_for(domain)]
        extra: dict[str, str] = {"memory": memory} if memory else {}
        return await producer.produce(
            snapshot=snapshot,
            query=query,
            domain=domain,
            case_id=case_id,
            feedback=feedback,
            **extra,
        )
