"""The HTTP client to the Mahsa (Rust) sidecar. This is the *only* path by which Maisha
gets a validated result. Maisha never decides Green/Yellow/Red itself."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.verdict import Figure, Verdict, build_verdict


class Banner(BaseModel):
    severity: str
    text: str
    citation: str
    action: str


class ResponseShape(BaseModel):
    status: str
    color: str
    layout: str
    requires_approval: bool
    banners: list[Banner] = Field(default_factory=list)
    global_score: float
    domain_score: float | None = None


class TriggeredRule(BaseModel):
    id: str
    domain: str
    severity: str
    description: str
    statute: str
    section: str
    action: str


class Validation(BaseModel):
    status: str
    triggered: list[TriggeredRule] = Field(default_factory=list)


class RecomputeClaim(BaseModel):
    """A figure Maisha computed, for Mahsa to independently recompute (§0.4). ``inputs`` fields
    match the recompute path's arguments (see dif/src/recompute)."""

    target: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    claimed_paise: int
    label: str | None = None


class RecomputeCheck(BaseModel):
    target: str
    label: str | None = None
    claimed_paise: int
    recomputed_paise: int | None = None  # None => Mahsa can't recompute → honest-pending (◐)
    matches: bool
    note: str

    @property
    def honest_pending(self) -> bool:
        """True when Mahsa could not independently recompute this figure (render ◐, not ✕)."""
        return self.recomputed_paise is None


class FoldResult(BaseModel):
    global_intent: list[float]
    global_dims: list[str]
    domain: str | None = None
    domain_intent: list[float] | None = None
    validation: Validation
    shape: ResponseShape
    rules_version: str
    recompute: list[RecomputeCheck] = Field(default_factory=list)

    def verdict(self, figures: list[Figure], *, org_id: str) -> Verdict:
        """Seal the Mahsa-recomputed ``figures`` into a Verdict for UI badges / PDF seals /
        audit chain. The rule-pack version comes from this validated result; ``org_id`` MUST be
        the session-context org (§0.8), never a request-body value."""
        return build_verdict(figures, self.rules_version, org_id=org_id)


class MahsaError(RuntimeError):
    """Raised when the sidecar is unreachable or returns a non-2xx response. We never
    silently fabricate a validation result when Mahsa is down — we fail loud."""


class MahsaClient:
    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(f"{self._base_url}/health")
                resp.raise_for_status()
            except httpx.HTTPError as exc:  # pragma: no cover - network edge
                raise MahsaError(f"Mahsa health check failed: {exc}") from exc
            return resp.json()

    async def fold(
        self,
        snapshot: dict[str, Any],
        *,
        domain: str | None = None,
        query: str | None = None,
        rules_version: str | None = None,
        recompute_claims: list[RecomputeClaim] | None = None,
    ) -> FoldResult:
        payload: dict[str, Any] = {"snapshot": snapshot}
        if domain is not None:
            payload["domain"] = domain
        if query is not None:
            payload["query"] = query
        if rules_version is not None:
            payload["rules_version"] = rules_version
        if recompute_claims:
            # Prime-Directive claims: Mahsa recomputes each and BLOCKs on a mismatch (§0.4).
            payload["recompute_claims"] = [
                c.model_dump(exclude_none=True) for c in recompute_claims
            ]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(f"{self._base_url}/fold", json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise MahsaError(f"Mahsa /fold failed: {exc}") from exc
        return FoldResult.model_validate(resp.json())
