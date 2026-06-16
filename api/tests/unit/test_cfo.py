"""CFO brief composition — pure over collected DomainHealth (no Mahsa needed)."""

from app.core.cfo import DailyBrief, DomainHealth, brief_payload, compose_brief


def _h(domain, score, status, approval=False, banners=None):
    return DomainHealth(domain, score, status, approval, banners or [])


def test_compose_brief_orders_worst_first_and_aggregates():
    health = [
        _h("treasury", 92.0, "green"),
        _h(
            "gst",
            40.0,
            "red",
            approval=True,
            banners=[{"text": "late", "citation": "x", "action": "y"}],
        ),
        _h("payables", 70.0, "yellow", approval=True),
    ]
    brief = compose_brief("2026-06-16", health)
    # worst first: red, then yellow, then green
    assert [h.domain for h in brief.scorecard] == ["gst", "payables", "treasury"]
    assert [h.domain for h in brief.needs_attention] == ["gst", "payables"]
    assert {h.domain for h in brief.approvals_pending} == {"gst", "payables"}
    # overall = mean(92, 40, 70) = 67.3
    assert brief.overall_score == 67.3


def test_compose_brief_all_green():
    brief = compose_brief("2026-06-16", [_h("treasury", 95.0, "green"), _h("gst", 88.0, "green")])
    assert brief.needs_attention == []
    assert brief.approvals_pending == []
    assert brief.overall_score == 91.5


def test_brief_payload_is_jsonable():
    brief = compose_brief("2026-06-16", [_h("treasury", 92.0, "green")])
    payload = brief_payload(brief)
    assert payload["as_of"] == "2026-06-16"
    assert payload["overall_score"] == 92.0
    assert payload["scorecard"][0]["domain"] == "treasury"
    assert payload["scorecard"][0]["color"] == "green"


def test_domain_health_color_mapping():
    assert DomainHealth("x", 1, "red", False).color == "red"
    assert DomainHealth("x", 1, "yellow", False).color == "amber"
    assert DomainHealth("x", 1, "green", False).color == "green"
    assert isinstance(compose_brief("d", []), DailyBrief)
