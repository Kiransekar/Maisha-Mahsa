"""Statutory document PDFs via ReportLab (pure-Python, BSD, no system deps). Builders are pure:
they take a fully-computed data dict (exact paise, computed upstream by the payroll engine) and
return PDF bytes. They never compute money — they only render it."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.money import Paise

_GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9ced6")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)


def _inr(paise: Any) -> str:
    return Paise(int(paise)).format_inr()


def _doc(buf: BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(buf, pagesize=A4, title=title, author="Maisha-Mahsa")


def payslip_pdf(data: dict) -> bytes:
    """Monthly payslip. ``data``: company, employee_name, employee_code, period,
    earnings/deductions (list of [label, paise]), gross, total_deductions, net."""
    buf = BytesIO()
    styles = getSampleStyleSheet()
    elems: list[Any] = [
        Paragraph(f"{data['company']} — Payslip", styles["Title"]),
        Paragraph(
            f"{data['employee_name']} ({data['employee_code']}) &nbsp; · &nbsp; {data['period']}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]
    earn = data["earnings"]
    ded = data["deductions"]
    rows = [["Earnings", "Amount (₹)", "Deductions", "Amount (₹)"]]
    for i in range(max(len(earn), len(ded))):
        e = earn[i] if i < len(earn) else ("", "")
        d = ded[i] if i < len(ded) else ("", "")
        rows.append([
            e[0], _inr(e[1]) if e[0] else "",
            d[0], _inr(d[1]) if d[0] else "",
        ])
    rows.append(["Gross", _inr(data["gross"]), "Total deductions", _inr(data["total_deductions"])])
    table = Table(rows, colWidths=[140, 110, 140, 110])
    table.setStyle(_GRID)
    net = Paragraph(f"<b>Net pay: {_inr(data['net'])}</b>", styles["Heading2"])
    elems += [table, Spacer(1, 12), net]
    _doc(buf, f"Payslip {data['period']}").build(elems)
    return buf.getvalue()


def audit_pack_pdf(pack: dict) -> bytes:
    """Audit Pack artifact (§WS8.1). ``pack`` is the output of
    :func:`app.core.audit_pack.build_audit_pack` — every figure renders with its badge TEXT
    (VERIFIED/PENDING/BLOCKED, straight from the §0.4-gated badge, never re-decided here) and
    the pack integrity hash is embedded on the cover."""
    # no cycle: audit_pack does not import pdf
    from app.core.audit_pack import SECTION_ORDER, badge_text, section_title

    buf = BytesIO()
    styles = getSampleStyleSheet()
    integrity = pack["integrity"]
    elems: list[Any] = [
        Paragraph("Maisha-Mahsa — Audit Pack", styles["Title"]),
        Paragraph(
            f"Organisation: {pack['org_id']} &nbsp; · &nbsp; "
            f"Rules version: {pack['rules_version']}",
            styles["Normal"],
        ),
        Spacer(1, 6),
        Table(
            [["Integrity hash (SHA-256)", integrity["hash"]]],
            colWidths=[140, 360],
            style=_GRID,
        ),
        Spacer(1, 6),
        Paragraph(
            "Badge legend: VERIFIED = Mahsa independently recomputed this figure to the paisa; "
            "PENDING = not yet independently recomputed; BLOCKED = recompute mismatch. "
            "No figure is marked VERIFIED without a Mahsa recomputation (Prime Directive §0.4).",
            styles["Italic"],
        ),
        Spacer(1, 12),
    ]
    for name in SECTION_ORDER:
        elems.append(Paragraph(section_title(name), styles["Heading2"]))
        figures = pack["sections"][name]
        if figures:
            rows = [["Particulars", "Amount (₹)", "Badge", "Evidence"]]
            rows += [
                [
                    Paragraph(f["label"], styles["BodyText"]),
                    _inr(f["value_paise"]),
                    badge_text(f["badge"]),
                    Paragraph(f["evidence_ref"], styles["BodyText"]),
                ]
                for f in figures
            ]
            table = Table(rows, colWidths=[210, 100, 70, 120])
            table.setStyle(_GRID)
            elems.append(table)
        note = pack["section_notes"].get(name)
        if note:
            elems.append(Spacer(1, 4))
            elems.append(Paragraph(note, styles["Italic"]))
        elems.append(Spacer(1, 10))
    if pack["pending_sections"]:
        elems.append(
            Paragraph(
                "Not yet included: " + ", ".join(pack["pending_sections"]) + ".",
                styles["Italic"],
            )
        )
    _doc(buf, "Audit Pack").build(elems)
    return buf.getvalue()


def form16_pdf(data: dict) -> bytes:
    """Form 16 — Part B (salary TDS certificate). ``data``: company, tan, employee_name, pan,
    financial_year, assessment_year, rows (list of [label, paise]), total_tax_deducted."""
    buf = BytesIO()
    styles = getSampleStyleSheet()
    elems: list[Any] = [
        Paragraph("FORM NO. 16 — Part B", styles["Title"]),
        Paragraph(
            "[See rule 31(1)(a)] · Certificate under section 203 of the Income-tax Act, 1961",
            styles["Normal"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Employer: {data['company']} (TAN: {data.get('tan') or '—'})<br/>"
            f"Employee: {data['employee_name']} (PAN: {data.get('pan') or '—'})<br/>"
            f"Financial Year: {data['financial_year']} &nbsp; · &nbsp; "
            f"Assessment Year: {data['assessment_year']}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]
    rows = [["Particulars", "Amount (₹)"]]
    rows += [[label, _inr(amount)] for label, amount in data["rows"]]
    rows.append(["Total tax deducted (TDS)", _inr(data["total_tax_deducted"])])
    table = Table(rows, colWidths=[360, 140])
    table.setStyle(_GRID)
    elems += [
        table,
        Spacer(1, 12),
        Paragraph(
            "This is Part B (salary breakup &amp; tax computation) generated from payroll. "
            "Part A (TDS deposited) is issued via TRACES.",
            styles["Italic"],
        ),
    ]
    _doc(buf, f"Form 16 {data['financial_year']}").build(elems)
    return buf.getvalue()
