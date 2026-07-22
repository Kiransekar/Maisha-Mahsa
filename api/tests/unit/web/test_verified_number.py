"""Verified-Number chip + Working panel (WS7.2 — docs/WS7_UX_RESEARCH.md T1: silent number-drift
is the #1 MSME trust-killer; a figure must be drillable from "here's a number" to "here's why
Mahsa stands behind it"). Renders partials/working_panel.html and the upgraded
partials/answer_card.html badge with sample data built the same way a real caller would: from
app.core.verify.FigureVerdict + app.core.verdict.Verdict + app.core.mahsa_client.RecomputeCheck —
never a fabricated badge."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.ask import Answer, Citation, Figure
from app.core.mahsa_client import RecomputeCheck
from app.core.verdict import Figure as VerdictFigure
from app.core.verdict import build_verdict
from app.core.verify import FigureVerdict

_WEB = Path(__file__).resolve().parents[3] / "app" / "web"
_TEMPLATES_DIR = _WEB / "templates"
_CSS_PATH = _WEB / "static" / "css" / "verified_number.css"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _panel_state(verdict: FigureVerdict) -> str:
    """The one honest mapping from a FigureVerdict to a panel state (§0.4: an unverified figure
    is ◐, never ✓)."""
    if verdict.verified:
        return "verified"
    if verdict.honest_pending:
        return "honest_pending"
    return "unbacked"


def _render_panel(**overrides: object) -> str:
    panel = {
        "label": "GST liability",
        "value": "₹5,000.00",
        "state": "verified",
        "inputs": [],
        "formula": None,
        "note": None,
        "citations": [],
        "documents": [],
        "verdict_hash": None,
        "rule_pack_version": None,
    }
    panel.update(overrides)
    return _env.get_template("partials/working_panel.html").render(panel=panel)


def test_verified_figure_shows_check_with_verification_class_and_matching_hash() -> None:
    fv = FigureVerdict(
        verified=True,
        blocked=False,
        honest_pending=False,
        check=RecomputeCheck(
            target="gst_liability",
            claimed_paise=500000,
            recomputed_paise=500000,
            matches=True,
            note="output_tax - itc_available, matched to the paisa",
        ),
    )
    sealed = build_verdict(
        [VerdictFigure(key="gst_liability", value_paise=500000)],
        "rp-2026.1",
        org_id="org-1",
    )
    inputs = [
        {"label": "Output tax", "value": "₹6,000.00"},
        {"label": "ITC available", "value": "₹1,000.00"},
    ]
    citations = [
        {"rule_id": "GST-039", "text": "GSTR-3B liability", "citation": "CGST Act 2017 / Sec 39"},
    ]
    html = _render_panel(
        state=_panel_state(fv),
        inputs=inputs,
        formula=fv.check.note,
        citations=citations,
        documents=[{"label": "GSTR-3B draft", "url": "/d/gst"}],
        verdict_hash=sealed.hash,
        rule_pack_version=sealed.rule_pack_version,
    )

    assert "✓" in html
    assert 'vglyph--verified' in html  # the VERIFICATION class family, not a money class
    assert "vmark--ok" not in html  # this is the new standalone chip, not the legacy badge
    assert "--c-green" not in html and "c-red" not in html  # never rendered as a money class
    assert "Output tax" in html and "₹6,000.00" in html  # inputs
    assert "output_tax - itc_available" in html  # formula/recompute
    assert "GST-039" in html and "CGST Act 2017 / Sec 39" in html  # citation: statute + section
    assert "GSTR-3B draft" in html  # linked document
    assert sealed.hash in html  # the hash shown matches the supplied verdict
    assert "Report an issue" in html


def test_honest_pending_shows_half_circle_not_check() -> None:
    fv = FigureVerdict(
        verified=False,
        blocked=False,
        honest_pending=True,
        check=RecomputeCheck(
            target="x", claimed_paise=100, recomputed_paise=None, matches=False, note=""
        ),
    )
    html = _render_panel(state=_panel_state(fv), verdict_hash=None)

    assert "◐" in html
    assert "✓" not in html  # honest-pending must never show the verified glyph
    assert "vglyph--honest_pending" in html
    assert "Mahsa cannot yet independently verify this figure" in html
    assert "Not yet sealed into a Mahsa verdict" in html  # no hash invented for an unsealed figure


def test_unbacked_shows_cross_not_check() -> None:
    fv = FigureVerdict(verified=False, blocked=True, honest_pending=False, check=None)
    html = _render_panel(state=_panel_state(fv))

    assert "✕" in html
    assert "✓" not in html
    assert "vglyph--unbacked" in html


def test_working_panel_empty_state_is_honest_not_fabricated() -> None:
    # No inputs/citations/documents/hash supplied -> every section says so plainly, nothing
    # invented (the hard rule: never fabricate a badge or its backing data).
    html = _render_panel(state="honest_pending")
    assert "No inputs recorded for this figure yet." in html
    assert "No statutory citation attached." in html
    assert "No documents linked." in html
    assert "Not yet sealed into a Mahsa verdict." in html


def test_answer_card_chip_preserves_legacy_glyphs_and_adds_working_panel() -> None:
    # Backward compatibility: the pre-existing ✓/○/⚠ glyphs, classes and title text (pinned by
    # tests/unit/web/test_ask.py) must still render — WS7.2 wraps the badge in a chip, it does
    # not replace it.
    figures = [
        Figure(
            "Recomputed figure", "₹1.00", True, "check",
            FigureVerdict(verified=True, blocked=False, honest_pending=False),
        ),
        Figure(
            "Pending figure", "₹2.00", True, "pending",
            FigureVerdict(verified=False, blocked=False, honest_pending=True),
        ),
        Figure(
            "Unbacked figure", "₹3.00", False, "warn",
            FigureVerdict(verified=False, blocked=True, honest_pending=False),
        ),
    ]
    citations = [Citation("GST-001", "GSTR-3B overdue", "CGST Act 2017 / Sec 47", "gst")]
    answer = Answer(
        query="q", domain="gst", figures=figures, citations=citations, provenance="test"
    )
    html = _env.get_template("partials/answer_card.html").render(answer=answer)

    assert "✓" in html and "○" in html and "⚠" in html
    assert "Mahsa cannot yet independently verify this figure" in html
    # The chip: each badge is now an expandable disclosure in the verification-token family.
    assert 'vnum vnum--verified' in html
    assert 'vnum vnum--honest_pending' in html
    assert 'vnum vnum--unbacked' in html
    # The working panel is present (drill-to-source) and carries the real citation through.
    assert "Report an issue" in html
    assert "GST-001" in html and "CGST Act 2017 / Sec 47" in html


def test_css_verification_family_stays_separate_from_money_colours() -> None:
    css = _CSS_PATH.read_text()
    # The actual fix: the legacy .vmark--* classes get repainted with --c-verify* tokens, scoped
    # under the new .vnum--<state> wrapper so it wins on specificity over app.css.
    assert ".vnum--verified .vmark--ok" in css and "var(--c-verify)" in css
    assert ".vnum--honest_pending .vmark--pending" in css and "var(--c-verify-pending)" in css
    assert ".vnum--unbacked .vmark--warn" in css and "var(--c-verify-fail)" in css
    # No verification-family selector may be painted with a money-direction token.
    for line in css.splitlines():
        if ".vnum--" in line or ".vglyph--" in line:
            assert "--c-green" not in line
            assert "--c-red" not in line
            assert "--c-amber" not in line


def test_lock_in_micro_interaction_is_subtle_and_accessible() -> None:
    css = _CSS_PATH.read_text()
    assert "@keyframes vnum-lock-in" in css
    assert "vnum--lock-in" in css
    assert "prefers-reduced-motion: reduce" in css
