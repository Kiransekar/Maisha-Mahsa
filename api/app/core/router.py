"""The DomainRouter: classify a free-text query to a domain by keyword match, and hold the
registry of domain services. Classification is deterministic — ties break by registration
order, and an unmatched query routes to ``None`` (global-only fold)."""

from __future__ import annotations

from app.core.domain import BaseDomainService


class DomainRouter:
    def __init__(self) -> None:
        self._services: dict[str, BaseDomainService] = {}

    def register(self, service: BaseDomainService) -> None:
        if service.domain in self._services:
            raise ValueError(f"domain '{service.domain}' already registered")
        self._services[service.domain] = service

    def get(self, domain: str) -> BaseDomainService | None:
        return self._services.get(domain)

    def domains(self) -> list[str]:
        return list(self._services)

    def classify(self, query: str) -> str | None:
        """Return the best-matching domain key, or ``None`` if nothing matches.

        Scores each domain by the number of its keywords present in the lower-cased query;
        highest score wins, registration order breaks ties.
        """
        q = query.lower()
        best: str | None = None
        best_score = 0
        for domain, svc in self._services.items():
            hits = sum(1 for kw in svc.keywords if kw in q)
            if hits > best_score:
                best, best_score = domain, hits
        return best
