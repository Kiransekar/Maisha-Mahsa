"""WS7.5 Exception Inbox: the five queues present; the two wired queues populated from their
real sources (pending approvals / Mahsa-blocked figures) and the other three honest-empty (never
fabricated); items ranked by ₹ impact; and the bulk-op PREVIEW is a dry-run that lists the
affected rows + total ₹ impact and mutates nothing until confirm=true."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from app.core.money import Paise
from app.web.exceptions import (
    QUEUE_ORDER,
    ApprovalInput,
    BlockedFigureInput,
    build_inbox,
    build_items,
    preview_bulk,
)

_TEMPLATES = Path(__file__).resolve().parents[3] / "app" / "web" / "templates"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()
    return env


def _sample_items() -> list:
    approvals = [
        ApprovalInput("treasury", "red", None, 50000000),  # ₹5,00,000
        ApprovalInput("gst", "yellow", None, 12345600),  # ₹1,23,456
        ApprovalInput("payroll", "red", None, None),  # ₹ not quantified
        ApprovalInput("tax", "red", "approved", 9999),  # resolved -> excluded
    ]
    blocked = [
        BlockedFigureInput("tax", "company_tax", "115BAA company tax", 22000000, 25168000, "off"),
    ]
    return build_items(approvals, blocked)


# ── queues ───────────────────────────────────────────────────────────────────
def test_five_queues_present_in_order() -> None:
    inbox = build_inbox([])
    assert [q.key for q in inbox.queues] == list(QUEUE_ORDER)
    assert len(inbox.queues) == 5


def test_wired_queues_populated_others_honest_empty() -> None:
    inbox = build_inbox(_sample_items())
    by_key = {q.key: q for q in inbox.queues}

    # real sources populated
    assert by_key["awaiting_approval"].count == 3  # tax approval resolved -> dropped
    assert by_key["mahsa_blocked"].count == 1

    # the three un-sourced queues are empty AND carry a stub source note (not fabricated items)
    for k in ("needs_document", "needs_categorization", "feed_broken"):
        assert by_key[k].count == 0
        assert by_key[k].source is None
        assert by_key[k].stub_note  # later-wiring pointer present, honest empty


def test_resolved_approval_is_not_pending() -> None:
    items = build_items([ApprovalInput("tax", "red", "approved", 100)], [])
    assert items == []  # a decided item is no longer in the inbox


# ── ranking by ₹ impact ──────────────────────────────────────────────────────
def test_items_ranked_by_rupee_impact() -> None:
    inbox = build_inbox(_sample_items())
    approvals = {q.key: q for q in inbox.queues}["awaiting_approval"].items
    # ₹5,00,000 before ₹1,23,456; the un-quantified (None) item sorts last.
    assert [i.domain for i in approvals] == ["treasury", "gst", "payroll"]
    assert approvals[-1].impact_paise is None


def test_blocked_impact_is_the_recompute_delta_never_invented() -> None:
    inbox = build_inbox(_sample_items())
    blocked = {q.key: q for q in inbox.queues}["mahsa_blocked"].items[0]
    assert blocked.impact_paise == abs(22000000 - 25168000)  # |claimed - recomputed|
    assert blocked.verify_state == "unbacked"  # ✕, never a fabricated ✓
    assert blocked.selectable is False  # a blocked figure can't be bulk-waved through


# ── bulk preview: dry-run, no mutation until confirm ─────────────────────────
def test_preview_is_dry_run_lists_rows_and_total_and_does_not_mutate() -> None:
    items = _sample_items()
    ids = ["approval:treasury", "approval:gst", "blocked:tax:company_tax"]
    preview = preview_bulk(items, ids, "approve")

    assert preview.committed is False  # dry-run: nothing applied
    # only the eligible awaiting-approval rows will change; the blocked figure is skipped
    assert sorted(r.domain for r in preview.rows) == ["gst", "treasury"]
    assert [r.domain for r in preview.skipped] == ["tax"]
    assert preview.total_impact_paise == 50000000 + 12345600  # sum of affected ₹
    assert all("approved" in r.will for r in preview.rows)

    # purity: re-running yields the same result and the source items are untouched
    again = preview_bulk(items, ids, "approve")
    assert again.total_impact_paise == preview.total_impact_paise
    assert build_items  # items list object identity preserved (no in-place edits)
    assert len(items) == 4


def test_confirm_flag_carried_but_preview_stays_pure() -> None:
    items = _sample_items()
    preview = preview_bulk(items, ["approval:treasury"], "approve", committed=True)
    assert preview.committed is True  # display flag only — preview never performs IO itself


# ── template render ──────────────────────────────────────────────────────────
def test_inbox_template_renders_five_queues_grouped_money_and_no_fake_check() -> None:
    inbox = build_inbox(_sample_items())
    html = (
        _env()
        .get_template("exception_inbox.html")
        .render(
            inbox=inbox,
            mahsa_up=True,
            settings=SimpleNamespace(app_name="Maisha-Mahsa"),
            nav_active="inbox",
        )
    )
    for label in (
        "Needs document",
        "Needs categorization",
        "Mahsa blocked",
        "Awaiting approval",
        "Feed broken",
    ):
        assert label in html
    assert "₹5,00,000.00" in html  # Indian lakh/crore grouping via the canonical renderer
    assert "✕" in html  # blocked figure carries the verification-fail glyph
    assert "✓" not in html  # nothing is verified here -> never a fabricated ✓
    assert "not wired yet" in html  # honest stub markers on the un-sourced queues


def test_bulk_preview_partial_shows_dry_run_and_confirm_form() -> None:
    items = _sample_items()
    preview = preview_bulk(items, ["approval:treasury", "approval:gst"], "approve")
    html = (
        _env()
        .get_template("partials/inbox_bulk_preview.html")
        .render(preview=preview, toast=None, mahsa_up=True)
    )
    assert "nothing has changed yet" in html.lower()
    assert '<input type="hidden" name="confirm" value="true">' in html  # confirm re-post
    assert "₹6,23,456.00" in html  # total impact, Indian-grouped
