"""Ask Maisha — the orchestrator behind the conversational surface. Classifies a free-text
query to a domain, builds the deterministic snapshot/facts, optionally folds via Mahsa (for a
verdict + statutory citations) and optionally drafts a narrative via the LLM — then assembles a
single :class:`Answer` view-model the UI renders.

It degrades cleanly, which matters for a single-binary product: with no LLM it returns the
deterministic figures; with Mahsa offline it omits the verdict; figures are always shown with a
verified mark so a number the engines didn't bless can never masquerade as fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.router import DomainRouter
from app.llm.client import build_client
from app.llm.maisha import ClaimProducer, MaishaGenerator
from app.llm.retry import allowed_values, generate_verified
from app.llm.schema import ActionClaim
from app.llm.tools import enrich
from app.web.format import fmt_value, humanize


@dataclass(frozen=True)
class Figure:
    label: str
    value: str
    verified: bool  # the number is backed by a deterministic fact (Golden Rule, made visible)


@dataclass(frozen=True)
class Citation:
    rule_id: str
    text: str
    citation: str  # "<statute> / <section>"
    domain: str


@dataclass
class Answer:
    query: str
    domain: str | None
    narrative: str = ""
    figures: list[Figure] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    status: str | None = None  # Mahsa verdict: green/yellow/red
    requires_approval: bool = False
    abstained: bool = False
    mahsa_up: bool = True
    provenance: str = ""


def _build_snapshot(
    service: BaseDomainService, session: Session, as_of: date | None
) -> dict[str, Any]:
    try:
        return service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        return service.build_snapshot(session)


def _figures(facts: dict[str, Any], claim: ActionClaim | None) -> list[Figure]:
    if claim is not None and claim.claims and not claim.abstained:
        allowed = allowed_values(facts)
        return [Figure(humanize(k), fmt_value(k, v), v in allowed) for k, v in claim.claims.items()]
    # No LLM draft (or it abstained): show the deterministic facts, all verified by construction.
    return [
        Figure(humanize(k), fmt_value(k, v), True)
        for k, v in sorted(facts.items())
        if k != "as_of"
    ]


async def answer_query(
    session: Session,
    *,
    query: str,
    registry: DomainRouter,
    settings: Any,
    as_of: date | None = None,
    mahsa: MahsaClient | None = None,
    generator: ClaimProducer | None = None,
) -> Answer:
    domain = registry.classify(query)
    if domain is None:
        return Answer(
            query=query,
            domain=None,
            narrative=(
                "I couldn't match that to a financial domain. Try mentioning cash, runway, "
                "GST, payroll, invoices, vendors, tax, equity or compliance."
            ),
            abstained=True,
        )

    service = registry.get(domain)
    assert service is not None  # classify only returns registered domains
    snapshot = _build_snapshot(service, session, as_of)
    facts = enrich(snapshot)

    # Mahsa fold for the verdict + citations; degrade if the sidecar is unreachable.
    fold = None
    mahsa_up = True
    client = mahsa or MahsaClient(settings.mahsa_url)
    try:
        fold = await client.fold(snapshot, domain=domain, query=query)
    except MahsaError:
        mahsa_up = False

    # Optional LLM draft (verified against facts when a fold is available).
    gen = generator
    if gen is None and settings.llm_provider != "off":
        is_ollama = settings.llm_provider == "ollama"
        model = settings.ollama_model if is_ollama else settings.claude_model
        gen = MaishaGenerator(
            build_client(settings),
            redact_pii=(settings.llm_provider == "claude"),
            label=f"{settings.llm_provider}:{model}",
        )

    claim: ActionClaim | None = None
    verified: bool | None = None
    if gen is not None:
        if fold is not None:
            draft = await generate_verified(
                gen,
                snapshot=snapshot,
                query=query,
                domain=domain,
                fold=fold,
                max_retries=settings.llm_max_retries,
            )
            claim, verified = draft.claim, draft.verified
        else:
            claim = await gen.produce(snapshot=snapshot, query=query, domain=domain)

    figures = _figures(facts, claim)
    citations = [
        Citation(t.id, t.description, f"{t.statute} / {t.section}", t.domain)
        for t in (fold.validation.triggered if fold else [])
    ]
    status = fold.validation.status if fold else None
    requires_approval = (fold.shape.requires_approval if fold else False) or (verified is False)

    label = getattr(gen, "label", None)
    if label:
        prov = f"Maisha · {domain} · drafted by {label}"
        if verified:
            prov += " · ✓ verified by Mahsa"
        elif verified is False:
            prov += " · pending review"
    else:
        prov = f"{domain} · deterministic figures"
    if not mahsa_up:
        prov += " · Mahsa offline"
    elif status:
        prov += f" · verdict {status}"

    return Answer(
        query=query,
        domain=domain,
        narrative=(claim.narrative if claim else ""),
        figures=figures,
        citations=citations,
        status=status,
        requires_approval=requires_approval,
        abstained=bool(claim.abstained) if claim else False,
        mahsa_up=mahsa_up,
        provenance=prov,
    )
