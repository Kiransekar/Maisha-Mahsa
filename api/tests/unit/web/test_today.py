"""WS7.3 Today view — the pure assembler + a full today.html render.

Grounds (docs/WS7_UX_RESEARCH.md): T1 (no fabricated ✓ — cash figures render honest-pending ◐),
T5/T6 (alert grammar: what/when/₹-consequence/action; ranked by ₹ impact), and the WS7.3
research challenge (penalties-avoided must be badge-backed or an explicit estimate, never
invented).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.core.approvals import ApprovalItem
from app.core.money import Paise
from app.db.models.shared import ComplianceCalendar
from app.db.models.treasury import BankAccount
from app.web.today import _MAX_LATE_FEE, build_today

AS_OF = date(2026, 7, 20)

_WEB = Path(__file__).resolve().parents[3] / "app" / "web"
_env = Environment(loader=FileSystemLoader(str(_WEB / "templates")), autoescape=True)
_env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()


def _seed_cash(session: Session) -> None:
    session.add(
        BankAccount(
            bank_name="HDFC", account_number="1", ifsc="HDFC0001", current_balance=5_00_00_000
        )
    )
    session.flush()


def _seed_compliance(session: Session) -> None:
    session.add_all(
        [
            # GST overdue, no stored penalty -> ported statutory late fee (accruing)
            ComplianceCalendar(domain="gst", form_name="GSTR-3B (Jun)", due_date="2026-07-13"),
            # ROC overdue WITH a real stored penalty -> that authoritative ₹ figure
            ComplianceCalendar(
                domain="roc", form_name="AOC-4", due_date="2026-07-13", penalty_amount=5_00_000
            ),
            # PF overdue, non-GST, no stored penalty -> honest-pending (no invented number)
            ComplianceCalendar(domain="pf", form_name="ECR", due_date="2026-07-13"),
            # a GST return already filed -> feeds penalties-avoided
            ComplianceCalendar(
                domain="gst", form_name="GSTR-3B (May)", due_date="2026-06-20", status="filed"
            ),
        ]
    )
    session.flush()


def test_cash_strip_is_three_honest_pending_panels(session: Session) -> None:
    _seed_cash(session)
    strip = build_today(session, AS_OF, [])["cash_strip"]
    assert [p["label"] for p in strip] == ["Cash on hand", "Monthly burn", "Runway"]
    # T1: no Mahsa verdict in a pure assembler => every figure is honest-pending, never ✓.
    assert all(p["state"] == "honest_pending" for p in strip)
    assert all(p["verdict_hash"] is None for p in strip)
    assert strip[0]["value"] == Paise(5_00_00_000).format_inr()  # canonical Indian grouping
    assert strip[2]["value"] == "∞ — no net burn"  # no burn seeded -> honest infinity


def test_cash_strip_carries_resolved_citation_anchors(session: Session) -> None:
    """CITE.P0-3 (§B4.1): once a bank statement is imported vault-first, the previously-empty
    working.documents block carries the rendered anchors — excerpt, /vault url, resolution."""
    from app.domains.treasury.service import TreasuryService

    acct = BankAccount(bank_name="HDFC", account_number="2", ifsc="HDFC0002")
    session.add(acct)
    session.flush()
    TreasuryService().import_csv(
        session,
        acct.id,
        "date,description,debit,credit\n2026-07-01,NEFT-000123,0,120000\n",
        file_name="HDFC-May.csv",
    )
    strip = build_today(session, AS_OF, [])["cash_strip"]
    for panel in strip:  # all three figures derive from the same statements
        [doc] = panel["documents"]
        assert doc["label"] == "HDFC-May.csv, row 2: 2026-07-01 NEFT-000123 ₹1,20,000.00 Cr"
        assert doc["resolution"] == "resolved"
        assert doc["url"].startswith("/d/vault?doc=")


def test_cash_strip_states_broken_citation_never_silently(session: Session) -> None:
    """§B2: tamper the stored source file → the anchor resolves BROKEN and the panel says so
    (the SPA badge downgrade keys off exactly this field)."""
    import hashlib

    from app.db.models.vault import Document
    from app.domains.treasury.service import TreasuryService

    acct = BankAccount(bank_name="HDFC", account_number="3", ifsc="HDFC0003")
    session.add(acct)
    session.flush()
    csv_text = "date,description,debit,credit\n2026-07-01,NEFT,0,120000\n"
    TreasuryService().import_csv(session, acct.id, csv_text, file_name="hdfc.csv")
    doc = session.get(Document, hashlib.sha256(csv_text.encode("utf-8")).hexdigest())
    assert doc is not None
    doc.raw_content = b"tampered"
    session.flush()

    strip = build_today(session, AS_OF, [])["cash_strip"]
    [entry] = strip[0]["documents"]
    assert entry["resolution"] == "broken"
    assert entry["note"] and "integrity" in entry["note"]


def test_needs_you_lists_unresolved_and_states_action(session: Session) -> None:
    approvals = [
        ApprovalItem(
            domain="gst",
            status="red",
            color="red",
            score=40.0,
            citations=[{"rule_id": "GST-001", "text": "GSTR-3B late", "citation": "CGST/47"}],
        ),
        ApprovalItem(  # already decided -> excluded
            domain="tax", status="red", color="red", score=None, resolution="approved"
        ),
    ]
    view = build_today(session, AS_OF, approvals)
    assert view["needs_you_empty"] is False
    assert len(view["needs_you"]) == 1
    item = view["needs_you"][0]
    assert item["domain"] == "gst"
    assert item["what"] == "GSTR-3B late"  # what happened
    assert item["action_href"] == "/approvals"  # one-tap action
    assert item["consequence_pending"] is True  # ₹ honest-pending, not an invented figure


def test_needs_you_honest_empty_state(session: Session) -> None:
    view = build_today(session, AS_OF, [])
    assert view["needs_you"] == []
    assert view["needs_you_empty"] is True


def test_trouble_radar_grammar_and_ranking(session: Session) -> None:
    _seed_compliance(session)
    trouble = build_today(session, AS_OF, [])["trouble"]
    assert len(trouble) == 3  # the filed GST return is not on the radar

    # ranked by ₹ impact desc: recorded ROC penalty (₹5,00,000) > GST late fee > honest-pending
    assert trouble[0]["domain"] == "roc"
    assert trouble[0]["consequence_paise"] == 5_00_000
    assert trouble[0]["consequence_kind"] == "recorded"

    gst = next(t for t in trouble if t["domain"] == "gst")
    from app.domains.gst import gst_calc

    assert gst["consequence_paise"] == gst_calc.late_fee_3b(7)  # 7 days overdue, real ported calc
    assert gst["consequence_kind"] == "accruing"

    pf = next(t for t in trouble if t["domain"] == "pf")
    assert pf["consequence_paise"] is None  # no invented number for a form with no fee source
    assert pf["consequence_kind"] == "pending"

    # grammar: every item carries what / when / action
    for t in trouble:
        assert t["what"] and t["when"] and t["action_href"].startswith("/d/")
        assert "OVERDUE" in t["when"]


def test_penalties_avoided_is_badge_backed_not_invented(session: Session) -> None:
    _seed_compliance(session)  # exactly one filed GST return
    pa = build_today(session, AS_OF, [])["penalties_avoided"]
    assert pa["estimate"] is True  # explicitly an estimate
    assert pa["backed"] is True
    assert pa["component_count"] == 1
    assert pa["amount_paise"] == _MAX_LATE_FEE  # 1 filed return x real ported statutory cap


def test_penalties_avoided_zero_when_nothing_filed(session: Session) -> None:
    pa = build_today(session, AS_OF, [])["penalties_avoided"]
    assert pa["amount_paise"] == 0  # never a fabricated non-zero counter
    assert pa["component_count"] == 0


def test_today_html_renders_all_regions_with_pending_glyph(session: Session) -> None:
    _seed_cash(session)
    _seed_compliance(session)
    view = build_today(session, AS_OF, [])
    html = _env.get_template("today.html").render(
        **view,
        settings=SimpleNamespace(app_name="Maisha-Mahsa", version="4.0"),
        mahsa_up=True,
        nav_active="today",
    )
    assert "Cash" in html and "Needs you" in html and "Trouble radar" in html
    assert "Penalties avoided" in html
    assert "◐" in html  # honest-pending glyph is present (cash strip is all pending)
    assert "Nothing needs you right now" in html  # honest empty state, no fake queue
    assert "EST." in html  # penalties-avoided flagged an estimate, not a ✓
