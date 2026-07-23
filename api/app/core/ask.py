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

from app.core import memory as org_memory
from app.core.domain import BaseDomainService
from app.core.mahsa_client import MahsaClient, MahsaError
from app.core.mahsa_coverage import is_recomputed
from app.core.principal import Principal
from app.core.router import DomainRouter
from app.core.verify import FigureVerdict
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
    # Tri-state honest-state mark (Prime Directive §0.4 — never ✓ without Mahsa recomputation):
    # "check" = Mahsa (Rust) independently recomputed this to the paisa; "pending" = a real,
    # fact-backed figure Mahsa can't yet independently verify (shown as-is, not hidden);
    # "warn" = not even backed by a deterministic fact.
    badge: str
    # The SAME FigureVerdict type app.core.verify's on-demand recompute path uses (WS7.2 follow-on,
    # WS7-E2E-OPEN item 4b) — `badge` above is a thin projection of this, not a second source of
    # truth. Threaded per-figure so the UI (and any future SPA consumer) can key off .verified /
    # .honest_pending / .blocked directly instead of parsing the display string.
    verdict: FigureVerdict


@dataclass(frozen=True)
class Citation:
    rule_id: str
    text: str
    citation: str  # "<statute> / <section>", or "audit <hash-prefix>" for recalled decisions
    domain: str
    # SPEC-MEMCITE-1.0 §A7: episodic recall renders as decision+hash pointing at the
    # tamper-evident chain, never a number-as-truth. None for statutory citations.
    audit_hash: str | None = None
    # SPEC-MEMCITE-1.0 §B4.3 (CITE.P0-3): an optional cell-level anchor — the answer layer
    # echoes cell anchors where a source row backs the citation (TableRAG grounding, §B1).
    # None wherever no anchor was minted: statutory cites and file-level refs stay coarse,
    # never fabricated precision (§B5). CITE.P1-2 threads real values through Ask.
    anchor: dict[str, Any] | None = None


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


def _verdict(target: str, fact_backed: bool) -> FigureVerdict:
    """The figure's FigureVerdict (app.core.verify — the same type the on-demand recompute path
    returns), built from the two signals already on hand here: is the number backed by a
    deterministic fact at all, and has Mahsa ever independently recomputed ``target``
    (mahsa_coverage, sourced from dif/tests/parity.rs PORTED). No new Mahsa call — this is the
    single place both ``.badge`` and the richer verdict are derived from, so they cannot drift.
    A number that isn't even fact-backed is BLOCKED outright (never shown as pending, let alone
    verified, per §0.4); a fact-backed number Mahsa hasn't ported yet is honest-pending, never
    upgraded to verified by omission."""
    if not fact_backed:
        return FigureVerdict(verified=False, blocked=True, honest_pending=False)
    if is_recomputed(target):
        return FigureVerdict(verified=True, blocked=False, honest_pending=False)
    return FigureVerdict(verified=False, blocked=False, honest_pending=True)


def _badge(target: str, fact_backed: bool) -> str:
    """"warn" if the figure isn't even backed by a deterministic fact (the more severe,
    genuinely-unbacked case); otherwise "check" only when Mahsa independently recomputed
    ``target``, else "pending" (honest, shown as-is). Thin projection of ``_verdict`` — that
    is the single source of truth, this just maps it to the display-string API callers pin."""
    v = _verdict(target, fact_backed)
    if v.blocked:
        return "warn"
    return "check" if v.verified else "pending"


def _figures(facts: dict[str, Any], claim: ActionClaim | None) -> list[Figure]:
    if claim is not None and claim.claims and not claim.abstained:
        allowed = allowed_values(facts)
        return [
            Figure(
                humanize(k),
                fmt_value(k, v),
                v in allowed,
                _badge(k, v in allowed),
                _verdict(k, v in allowed),
            )
            for k, v in claim.claims.items()
        ]
    # No LLM draft (or it abstained): the deterministic facts are all fact-backed ("verified"
    # in that sense), but that alone doesn't earn a ✓ — the badge still asks mahsa_coverage
    # whether Rust independently recomputed each one.
    return [
        Figure(humanize(k), fmt_value(k, v), True, _badge(k, True), _verdict(k, True))
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
    principal: Principal | None = None,
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

    # SPEC-MEMCITE-1.0 §A7: with a verified caller, the org profile + CFO posture block is
    # threaded to the drafting layer as CONTEXT (screened + labeled inside the generator;
    # never merged into `facts`, so a memory figure can never verify — §A4). Principal-only
    # org scoping (§A3): the org comes from the JWT-verified Principal, nowhere else.
    mem: str | None = None
    if principal is not None:
        mem = org_memory.profile_text(session, principal) or None
    # Passed as **kwargs only when present so ClaimProducer stubs predating `memory` still work.
    extra: dict[str, str] = {"memory": mem} if mem else {}

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
                memory=mem,
            )
            claim, verified = draft.claim, draft.verified
        else:
            claim = await gen.produce(snapshot=snapshot, query=query, domain=domain, **extra)

    figures = _figures(facts, claim)
    citations = [
        Citation(t.id, t.description, f"{t.statute} / {t.section}", t.domain)
        for t in (fold.validation.triggered if fold else [])
    ]
    # Episodic recall (§A1 type 3): lexical, LLM-free, over the caller's org's OWN sealed
    # chain — works identically with the LLM off. Rendered as decision+hash citations.
    if principal is not None:
        citations += [
            Citation(
                rule_id=f"decision:{r['action']}",
                text=r["decision"],
                citation=f"audit {r['audit_hash'][:12]}",
                domain=r["domain"],
                audit_hash=r["audit_hash"],
            )
            for r in org_memory.recall_decisions(session, principal, query)
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
