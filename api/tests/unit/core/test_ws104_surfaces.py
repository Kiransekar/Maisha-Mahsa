"""WS10.4 — the disclaimer must actually RENDER on the specified surfaces, byte-exact.

``test_legal.py`` pins the constant itself; these tests pin the wiring — the failure mode they
exist for is a surface quietly dropping (or paraphrasing) the line while the constant stays
green. Each assertion targets one rendering path:

* the shared PDF footer callback (one build path for payslip / audit pack / Form 16 —
  ``app.core.pdf._build`` routes every builder through it, so this single check covers all
  three PDFs; the drawn text is asserted through the callback because ReportLab compresses
  page streams, which would make a bytes-level scan of the PDF silently vacuous);
* the audit-pack CSV-zip export cover sheet;
* the HTMX base template (every screen extends it);
* the SPA shell footnote (mirrored assertion lives in ``frontend/src/components/
  Shell.test.tsx``; the source-level check here catches a reword that a vitest-less CI slice
  would miss).
"""

from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

from app.core import pdf
from app.core.audit_pack import build_audit_pack, pack_to_csv_zip
from app.core.legal import DISCLAIMER_TEXT

REPO_ROOT = Path(__file__).resolve().parents[4]

# Minimal valid entity_data (shape per app.core.audit_pack docstring; independent copy — this
# file deliberately does not import from another test module, tests/ is not a package).
ENTITY_DATA = {
    "org_id": "org_alpha",
    "rules_version": "2026.07.0",
    "trial_balance": {"total_debit": 500_000, "total_credit": 500_000, "diff": 0},
    "profit_and_loss": {"income": 300_000, "expense": 180_000, "net_profit": 120_000},
    "balance_sheet": {
        "assets": 800_000,
        "liabilities": 200_000,
        "equity": 480_000,
        "retained_profit": 120_000,
    },
    "general_ledger": [{"code": "1000", "name": "Cash", "closing_balance": 800_000}],
    "statutory_registers": {
        "tds_returns": [],
        "gst_returns": [],
        "payroll": {
            "monthly_burn": 1_200_000,
            "lwf_due_paise": 4_000,
            "monthly_bonus_required_paise": 83_300,
        },
    },
    "form_26as_reconciliation": None,
    "msme_ageing": {
        "ap_aging": {
            "buckets": {"0-30": 100_000, "31-60": 0, "61-90": 0, "90+": 0},
            "total_outstanding": 100_000,
        },
        "msme_max_days_unpaid": 12,
    },
}


class _RecordingCanvas:
    """Records drawn strings — the assertion surface for the footer callback."""

    def __init__(self) -> None:
        self.drawn: list[str] = []

    def saveState(self) -> None:  # noqa: N802 — ReportLab API casing
        pass

    def restoreState(self) -> None:  # noqa: N802
        pass

    def setFont(self, _name: str, _size: float) -> None:  # noqa: N802
        pass

    def drawCentredString(self, _x: float, _y: float, text: str) -> None:  # noqa: N802
        self.drawn.append(text)


def test_pdf_footer_draws_the_byte_exact_disclaimer():
    canvas = _RecordingCanvas()
    pdf._disclaimer_footer(canvas, None)
    assert canvas.drawn == [DISCLAIMER_TEXT]


def test_every_pdf_builder_routes_through_the_footered_build_path():
    """Deleting the footer wiring from ONE builder must fail here: no builder may call
    ReportLab's ``build`` directly — ``_build`` is the only build path (it is where the
    ``onFirstPage``/``onLaterPages`` footer is attached)."""
    source = Path(pdf.__file__).read_text(encoding="utf-8")
    assert source.count(".build(") == 1, (
        "app/core/pdf.py must contain exactly one ReportLab .build( call — inside _build(), "
        "which attaches the WS10.4 disclaimer footer. A builder bypassing _build() ships a "
        "PDF without the disclaimer."
    )
    assert "onFirstPage=_disclaimer_footer" in source
    assert "onLaterPages=_disclaimer_footer" in source


def test_audit_pack_csv_cover_carries_the_disclaimer():
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    blob = pack_to_csv_zip(pack)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        cover = zf.read("00_cover.csv").decode("utf-8")
    assert DISCLAIMER_TEXT in cover


def test_htmx_base_template_carries_the_disclaimer():
    base = (REPO_ROOT / "api/app/web/templates/base.html").read_text(encoding="utf-8")
    assert DISCLAIMER_TEXT in base


def test_spa_shell_carries_the_disclaimer():
    # JSX collapses the line break + indentation to a single space when rendering, so the
    # source is normalised the same way before comparing against the byte-exact constant.
    shell = (REPO_ROOT / "frontend/src/components/Shell.tsx").read_text(encoding="utf-8")
    normalised = " ".join(shell.split())
    assert DISCLAIMER_TEXT in normalised
