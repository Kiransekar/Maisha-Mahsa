"""The CFO layer: collect every domain's health through Mahsa into one scorecard, and
compose the daily brief (PRD §6.1 — the Domain Health Dashboard).

`collect_health` is the single place that folds all 12 domains; `compose_brief` is a pure
function over the collected health, so the brief content is fully testable without Mahsa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.mahsa_client import MahsaClient
from app.core.router import DomainRouter


@dataclass
class DomainHealth:
    domain: str
    score: float | None  # 0..100 (domain sub-vector score, else global)
    status: str  # green / yellow / red
    requires_approval: bool
    banners: list[dict] = field(default_factory=list)

    @property
    def color(self) -> str:
        return {"green": "green", "yellow": "amber", "red": "red"}.get(self.status, "green")


async def collect_health(
    session: Session, mahsa: MahsaClient, registry: DomainRouter, *, as_of: date | None = None
) -> list[DomainHealth]:
    """Fold every registered domain and collect its health. Raises ``MahsaError`` if the
    sidecar is unreachable (the caller decides whether to degrade)."""
    out: list[DomainHealth] = []
    for domain in registry.domains():
        service = registry.get(domain)
        if service is None:
            continue
        try:
            snapshot = service.build_snapshot(session, as_of)  # type: ignore[call-arg]
        except TypeError:
            snapshot = service.build_snapshot(session)
        fold = await mahsa.fold(snapshot, domain=service.domain)
        score = fold.shape.domain_score
        if score is None:
            score = fold.shape.global_score
        out.append(
            DomainHealth(
                domain=domain,
                score=round(score, 1) if score is not None else None,
                status=fold.validation.status,
                requires_approval=fold.shape.requires_approval,
                banners=[b.model_dump() for b in fold.shape.banners],
            )
        )
    return out


@dataclass
class DailyBrief:
    as_of: str
    scorecard: list[DomainHealth]
    needs_attention: list[DomainHealth]
    approvals_pending: list[DomainHealth]
    overall_score: float | None


def compose_brief(as_of: str, health: list[DomainHealth]) -> DailyBrief:
    """Compose the 8pm CFO brief from collected health. Pure."""
    scored = [h.score for h in health if h.score is not None]
    overall = round(sum(scored) / len(scored), 1) if scored else None
    # Worst first in the scorecard (red, then yellow, then green); stable by domain name.
    order = {"red": 0, "yellow": 1, "green": 2}
    scorecard = sorted(health, key=lambda h: (order.get(h.status, 3), h.domain))
    needs_attention = [h for h in scorecard if h.status in ("red", "yellow")]
    approvals_pending = [h for h in scorecard if h.requires_approval]
    return DailyBrief(
        as_of=as_of,
        scorecard=scorecard,
        needs_attention=needs_attention,
        approvals_pending=approvals_pending,
        overall_score=overall,
    )


def brief_payload(brief: DailyBrief) -> dict[str, Any]:
    """JSON-able view of a brief (for templates and API responses)."""

    def row(h: DomainHealth) -> dict[str, Any]:
        return {
            "domain": h.domain,
            "score": h.score,
            "status": h.status,
            "color": h.color,
            "requires_approval": h.requires_approval,
            "banners": h.banners,
        }

    return {
        "as_of": brief.as_of,
        "overall_score": brief.overall_score,
        "scorecard": [row(h) for h in brief.scorecard],
        "needs_attention": [row(h) for h in brief.needs_attention],
        "approvals_pending": [row(h) for h in brief.approvals_pending],
    }
