"""The eval runner: for each case, seed a fresh in-memory DB, build the domain snapshot, ask
the producer for a claim ``k`` times (pass^k), and score the claim. CLI entry point for
``make eval``.

The runner never touches Mahsa's verdict logic — it exercises the *generator* side. The
Mahsa-consistency check (folding the snapshot through the real binary and matching
``expected_status``) is an integration concern layered on later; the pure scorers here run
with no network and no model.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  registers all models on Base.metadata
from app.core.domain import BaseDomainService
from app.db.base import Base
from app.domains import build_registry

from .report import render_json, render_text
from .scorers import ALL_SCORERS, ScoreResult
from .types import ClaimProducer, EvalCase, ScriptedProducer

SessionFactory = Callable[[], Session]


def default_session_factory() -> Session:
    """A throwaway in-memory SQLite session with the full schema — mirrors the test fixture
    in ``tests/conftest.py`` so cases seed data exactly as the unit tests do."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    return factory()


@dataclass
class CaseResult:
    id: str
    domain: str
    k: int
    consistent: bool
    scores: list[ScoreResult]

    @property
    def passed(self) -> bool:
        return self.consistent and all(s.passed for s in self.scores)


def _build_snapshot(service: BaseDomainService, session: Session, as_of: date | None) -> dict:
    # Some services accept an optional as_of (treasury, gst); fall back gracefully — same
    # shim as core.loop.run_loop.
    try:
        return service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        return service.build_snapshot(session)


async def run_case(
    case: EvalCase,
    producer: ClaimProducer,
    *,
    session_factory: SessionFactory = default_session_factory,
) -> CaseResult:
    registry = build_registry()
    service = registry.get(case.domain)
    if service is None:
        raise ValueError(f"unknown domain '{case.domain}' in case '{case.id}'")

    canonicals: list[str] = []
    first_claim = None
    for _ in range(max(1, case.k)):
        session = session_factory()
        try:
            case.seed(session)
            session.flush()
            snapshot = _build_snapshot(service, session, case.as_of)
        finally:
            session.close()
        claim = await producer.produce(
            snapshot=snapshot, query=case.query, domain=case.domain, case_id=case.id
        )
        canonicals.append(claim.canonical())
        if first_claim is None:
            first_claim = claim

    assert first_claim is not None  # k >= 1
    consistent = len(set(canonicals)) == 1
    scores = [scorer(first_claim, case.expect) for scorer in ALL_SCORERS]
    return CaseResult(
        id=case.id, domain=case.domain, k=case.k, consistent=consistent, scores=scores
    )


async def run_all(
    cases: Iterable[EvalCase],
    producer: ClaimProducer,
    *,
    session_factory: SessionFactory = default_session_factory,
) -> list[CaseResult]:
    return [await run_case(c, producer, session_factory=session_factory) for c in cases]


def _load_cases(domain: str | None) -> list[EvalCase]:
    from .cases import ALL_CASES

    if domain is None:
        return list(ALL_CASES)
    selected = [c for c in ALL_CASES if c.domain == domain]
    if not selected:
        raise SystemExit(f"no eval cases for domain '{domain}'")
    return selected


def _build_producer(provider: str, cases: list[EvalCase]) -> ClaimProducer:
    """``stub`` returns the canned-claim producer (the CI gate, no model). ``ollama``/``claude``
    build the real :class:`MaishaGenerator` so the same cases become a live model-quality gate."""
    if provider == "stub":
        return ScriptedProducer({c.id: c.stub_claim for c in cases})
    from app.config import get_settings
    from app.llm.client import build_client
    from app.llm.maisha import MaishaGenerator

    settings = get_settings().model_copy(update={"llm_provider": provider})
    model = settings.ollama_model if provider == "ollama" else settings.claude_model
    return MaishaGenerator(
        build_client(settings), redact_pii=(provider == "claude"), label=f"{provider}:{model}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.harness", description="Maisha golden-eval gate")
    parser.add_argument("--all", action="store_true", help="run every domain's cases")
    parser.add_argument("--domain", help="run only this domain's cases")
    parser.add_argument(
        "--report", choices=["text", "json"], default="text", help="output format"
    )
    parser.add_argument(
        "--provider",
        choices=["stub", "ollama", "claude"],
        default="stub",
        help="stub = canned claims (CI gate); ollama/claude = drive the real model",
    )
    args = parser.parse_args(argv)
    if not args.all and not args.domain:
        parser.error("pass --all or --domain <name>")

    cases = _load_cases(args.domain if not args.all else None)
    producer = _build_producer(args.provider, cases)
    results = asyncio.run(run_all(cases, producer))

    output = render_json(results) if args.report == "json" else render_text(results)
    print(output)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
