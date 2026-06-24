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
