"""Ask Maisha orchestrator: assembles a verified Answer from facts + Mahsa fold + LLM draft,
and degrades cleanly when a domain can't be classified."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.core.ask import Answer, Figure, _badge, _figures, _verdict, answer_query
from app.core.mahsa_client import FoldResult, ResponseShape, TriggeredRule, Validation
from app.core.mahsa_coverage import load_coverage
from app.db.models.gst import GstReturn
from app.domains import build_registry
from app.llm.schema import ActionClaim
from app.web.format import humanize

_SETTINGS = SimpleNamespace(
    mahsa_url="http://unused",
    llm_provider="off",
    llm_max_retries=2,
    ollama_model="m",
    claude_model="c",
)


class _FakeMahsa:
    def __init__(self, triggered: list[TriggeredRule]) -> None:
        self._t = triggered

    async def fold(
        self,
        snapshot: dict[str, Any],
        *,
        domain=None,
        query=None,
        rules_version=None,
        recompute_claims=None,
    ) -> FoldResult:
        status = "red" if self._t else "green"
        return FoldResult(
            global_intent=[0.0],
            global_dims=["x"],
            validation=Validation(status=status, triggered=self._t),
            shape=ResponseShape(
                status=status,
                color=status,
                layout="default",
                requires_approval=bool(self._t),
                global_score=70.0,
            ),
            rules_version="test",
        )


class _CannedGen:
    label = "test:model"

    def __init__(self, claim: ActionClaim) -> None:
        self._claim = claim

    async def produce(  # noqa: ANN001
        self, *, snapshot, query, domain, case_id="", feedback=None
    ) -> ActionClaim:
        return self._claim


def _seed_late_gst(session: Session) -> None:
    session.add(
        GstReturn(
            return_type="GSTR-3B",
            filing_period="2026-05",
            due_date="2026-06-20",
            status="pending",
        )
    )
    session.flush()


@pytest.mark.asyncio
async def test_answer_query_verified_with_citation(session: Session) -> None:
    _seed_late_gst(session)
    registry = build_registry()
    rule = TriggeredRule(
        id="GST-001",
        domain="gst",
        severity="block",
        description="GSTR-3B overdue",
        statute="CGST Act 2017",
        section="Sec 47 / Rule 61",
        action="file",
    )
    # claim restates a backed fact (days late = 20 as of 2026-07-10 is what build_snapshot gives,
    # but we fold/produce against the seeded snapshot whose value the generator must match)
    # as_of 2026-07-10 → snapshot says 20 days late, so the claim's "20" is a backed fact.
    claim = ActionClaim(domain="gst", narrative="Overdue.", claims={"gstr3b_days_late": "20"})
    gen = _CannedGen(claim)
    answer = await answer_query(
        session,
        query="is our gstr-3b on time?",
        registry=registry,
        settings=_SETTINGS,
        as_of=date(2026, 7, 10),
        mahsa=_FakeMahsa([rule]),
        generator=gen,
    )
    assert answer.domain == "gst"
    assert answer.status == "red"
    assert answer.requires_approval is True
    assert any(c.rule_id == "GST-001" for c in answer.citations)
    assert "verified by Mahsa" in answer.provenance
    assert answer.figures  # at least one figure rendered


@pytest.mark.asyncio
async def test_answer_query_degraded_without_llm_or_mahsa(session: Session) -> None:
    # No generator, Mahsa raises -> deterministic facts only, flagged offline.
    from app.core.mahsa_client import MahsaError

    class _DownMahsa:
        async def fold(self, *a, **k):  # type: ignore[no-untyped-def]
            raise MahsaError("down")

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_DownMahsa(),  # type: ignore[arg-type]
    )
    assert answer.domain == "treasury"
    assert answer.mahsa_up is False
    assert answer.status is None
    assert all(f.verified for f in answer.figures)  # deterministic facts are verified
    assert "deterministic figures" in answer.provenance


@pytest.mark.asyncio
async def test_answer_query_unroutable_abstains(session: Session) -> None:
    answer = await answer_query(
        session,
        query="hello there",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_FakeMahsa([]),
    )
    assert answer.domain is None
    assert answer.abstained is True
    assert answer.figures == []


# ---- CITE.P1-2 (§B4.3): Ask citations carry cell-level anchors ----------------------------


@pytest.mark.asyncio
async def test_treasury_answer_citations_carry_anchors_from_imported_rows(
    session: Session,
) -> None:
    """A treasury answer whose figures derive from an imported bank statement echoes each
    anchored row as a citation carrying the full §B1 anchor struct — excerpt, /d/vault
    deep-link, live resolution state. Statutory citations keep anchor=None (§B5)."""
    from app.db.models.treasury import BankAccount
    from app.domains.treasury.service import TreasuryService

    acct = BankAccount(bank_name="HDFC", account_number="9", ifsc="HDFC0009")
    session.add(acct)
    session.flush()
    TreasuryService().import_csv(
        session,
        acct.id,
        "date,description,debit,credit\n2026-07-01,NEFT-000123,0,120000\n",
        file_name="HDFC-May.csv",
    )

    answer = await answer_query(
        session,
        query="what's our runway?",
        registry=build_registry(),
        settings=_SETTINGS,
        mahsa=_FakeMahsa([]),
    )
    assert answer.domain == "treasury"
    anchored = [c for c in answer.citations if c.anchor is not None]
    assert len(anchored) == 1
    c = anchored[0]
    assert c.text == "HDFC-May.csv, row 2: 2026-07-01 NEFT-000123 ₹1,20,000.00 Cr"
    assert c.citation == "HDFC-May.csv, row 2"
    assert c.rule_id == f"source:{c.anchor['doc_sha256'][:12]}"
    assert c.anchor["locator"] == {"kind": "csv_row", "source_row": 2}
    assert c.anchor["resolution"] == "resolved"
    assert c.anchor["url"] == f"/d/vault?doc={c.anchor['doc_sha256']}"
    # And the HTMX card renders the anchored citation as a working-panel document entry
    # with the deep-link — the same surface the SPA maps from `anchor`.
    html = _env.get_template("partials/answer_card.html").render(answer=answer)
    assert f"/d/vault?doc={c.anchor['doc_sha256']}" in html
    assert "HDFC-May.csv, row 2" in html


@pytest.mark.asyncio
async def test_non_treasury_answer_citations_have_no_anchor(session: Session) -> None:
    _seed_late_gst(session)
    answer = await answer_query(
        session,
        query="is our gstr-3b on time?",
        registry=build_registry(),
        settings=_SETTINGS,
        as_of=date(2026, 7, 10),
        mahsa=_FakeMahsa([]),
    )
    assert answer.domain == "gst"
    # GST figures come from typed input — no anchor exists, none is fabricated (§B5).
    assert all(c.anchor is None for c in answer.citations)


# ---- WS3.5b: honest-state badge, tri-state driven off mahsa_coverage (§0.4) ----------------

# Pull a ported and an unported target straight from the coverage map itself (not a literal
# guess) so this test tracks mahsa_coverage.json rather than assuming any specific target.
_COVERAGE_TARGETS = load_coverage()["targets"]
_PORTED_TARGET = next(name for name, e in _COVERAGE_TARGETS.items() if e["ported"])
_UNPORTED_TARGET = next(name for name, e in _COVERAGE_TARGETS.items() if not e["ported"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "app" / "web" / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def test_badge_is_coverage_driven_not_hardcoded() -> None:
    # A fact-backed figure whose key IS a Mahsa-recomputed target -> "check".
    assert _badge(_PORTED_TARGET, fact_backed=True) == "check"
    # A fact-backed figure whose key is a known-but-not-yet-ported target -> "pending".
    assert _badge(_UNPORTED_TARGET, fact_backed=True) == "pending"
    # An unknown target defaults to "pending" too (mahsa_coverage's own honest default),
    # never "check" by omission.
    assert _badge("not_a_real_target", fact_backed=True) == "pending"
    # Not even fact-backed -> "warn", regardless of what mahsa_coverage says.
    assert _badge(_PORTED_TARGET, fact_backed=False) == "warn"


def test_answer_card_renders_hollow_circle_for_pending_and_check_for_recomputed() -> None:
    figures = [
        Figure(
            "Recomputed figure",
            "₹1.00",
            True,
            _badge(_PORTED_TARGET, True),
            _verdict(_PORTED_TARGET, True),
        ),
        Figure(
            "Pending figure",
            "₹2.00",
            True,
            _badge(_UNPORTED_TARGET, True),
            _verdict(_UNPORTED_TARGET, True),
        ),
        Figure(
            "Unbacked figure",
            "₹3.00",
            False,
            _badge(_PORTED_TARGET, False),
            _verdict(_PORTED_TARGET, False),
        ),
    ]
    answer = Answer(
        query="q",
        domain="payroll",
        figures=figures,
        provenance="test",
    )
    html = _env.get_template("partials/answer_card.html").render(answer=answer)

    assert "✓" in html  # recomputed by Mahsa
    assert "○" in html  # honest-pending: shown as-is, not yet independently verifiable
    assert "⚠" in html  # genuinely unbacked
    assert "Mahsa cannot yet independently verify this figure" in html


# ---- WS7-E2E-OPEN(4b): per-figure FigureVerdict threaded through ask.py -------------------


def test_figures_thread_real_verdict_for_ported_and_unported() -> None:
    """Response-shape check: ``_figures`` (what ``answer_query`` calls to build
    ``Answer.figures``) attaches the ACTUAL app.core.verify.FigureVerdict per figure — a
    response with one ported/verified target and one unported/honest-pending target shows both
    states correctly, and the unbacked figure is never mistaken for verified."""
    facts = {"some_fact": "20"}
    claim = ActionClaim(
        domain="gst",
        narrative="x",
        claims={_PORTED_TARGET: "20", _UNPORTED_TARGET: "20", "invented_number": "999"},
    )
    figures = {f.label: f for f in _figures(facts, claim)}

    ported = figures[humanize(_PORTED_TARGET)]
    assert ported.verdict.verified is True
    assert ported.verdict.blocked is False
    assert ported.verdict.honest_pending is False
    assert ported.badge == "check"

    unported = figures[humanize(_UNPORTED_TARGET)]
    assert unported.verdict.honest_pending is True
    assert unported.verdict.verified is False  # never a fabricated verified
    assert unported.badge == "pending"

    unbacked = figures[humanize("invented_number")]
    assert unbacked.verdict.blocked is True
    assert unbacked.verdict.verified is False
    assert unbacked.badge == "warn"


def test_verdict_lookup_is_real_not_hardcoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tamper/mutation check: if the mahsa_coverage lookup behind ``_verdict`` were dropped
    (hardcoded to always say "recomputed"), the unported target above would wrongly flip to
    verified — proving the correctness test isn't vacuous."""
    import app.core.ask as ask_mod

    assert _verdict(_UNPORTED_TARGET, fact_backed=True).verified is False  # true today

    monkeypatch.setattr(ask_mod, "is_recomputed", lambda target: True)  # drop the real lookup
    tampered = ask_mod._verdict(_UNPORTED_TARGET, fact_backed=True)
    assert tampered.verified is True  # ... and the wrong answer proves the lookup was live
