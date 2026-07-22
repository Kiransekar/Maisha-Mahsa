"""Audit Pack generator (MMX-1.0 §WS8.1 — core slice).

Assembles the four core statements a CA needs first — Trial Balance, P&L, Balance Sheet,
General Ledger summary — into one structured, tamper-evident dict. Every line figure carries
a badge (``verified`` / ``honest_pending`` via :mod:`app.core.mahsa_coverage`, per the Prime
Directive §0.4: nothing shows verified unless Mahsa independently recomputed it) and an
``evidence_ref`` pointing back to the domain computation that produced it.

This module is pure and DB-free by design (same shape as :mod:`app.core.verdict`): callers
(ledger/gst/payables/payroll/tax services, via a router in a follow-on ticket) assemble
``entity_data`` from their own session-backed methods — e.g. ``LedgerService.trial_balance()``,
``.profit_and_loss()``, ``.balance_sheet()``, and a per-account closing-balance list for the GL
summary — and this module only shapes, badges, and seals the result.

``entity_data`` shape::

    {
        "org_id": str,
        "rules_version": str,
        "trial_balance": {"total_debit": int, "total_credit": int, "diff": int},
        "profit_and_loss": {"income": int, "expense": int, "net_profit": int},
        "balance_sheet": {"assets": int, "liabilities": int, "equity": int,
                           "retained_profit": int},
        "general_ledger": [{"code": str, "name": str, "closing_balance": int}, ...],
    }

``trial_balance``, ``profit_and_loss``, and ``balance_sheet`` may also carry an optional
``"extra_figures"`` list of
``{"label": str, "value_paise": int, "target": str, "evidence_ref": str}`` — this is how a
statutory figure genuinely recomputed elsewhere (e.g. tax/payroll's ``tds_on_payment`` or
``esi``) gets folded into the pack under its OWN Mahsa coverage target, instead of every line
defaulting to the ledger's own ``honest_pending`` bookkeeping target. Never invent a target
name that maps to a real oracle key unless the figure genuinely is that computation — a wrong
target here would misreport a badge, which is exactly what §0.4 forbids.

WS8.1 remainder (this ticket) adds three more sections — all figures pulled from the domain
services that already computed them, never recomputed here:

* ``statutory_registers`` — filed TDS returns (tax), filed GST returns (gst), and the payroll
  register summary (payroll ``build_snapshot`` metrics). Input shape::

      "statutory_registers": {
          "tds_returns": [{"return_type", "quarter", "total_deducted",
                            "late_filing_fee", "status"}, ...],
          "gst_returns": [{"return_type", "filing_period", "tax_payable",
                            "late_fee", "interest", "status"}, ...],
          "payroll": {"lwf_due_paise": int, "monthly_bonus_required_paise": int,
                       "monthly_burn": int},
      }

  A TDS return's ``late_filing_fee`` genuinely IS the ``late_fee_234e`` computation
  (``tax_calc.late_fee_234e`` via ``TaxService.file_tds_return``), so it carries that coverage
  target. GST ``late_fee``/``interest`` stay on unported targets — see
  ``GstService.recompute_claims`` for why the late fee is deliberately not claimed.

* ``form_26as_reconciliation`` — the OUTPUT of ``tax_calc.reconcile_26as`` (per-TAN matched /
  mismatched / one-sided figures). Optional: when no 26AS statement has been loaded the section
  is honest-empty with a note (WS7 invariant: honest-empty ≠ zero), never a vacuous
  "reconciled".

* ``msme_ageing`` — ``PayablesService.ap_aging`` buckets + ``msme_max_days_unpaid`` (MSMED Act
  s.15 45-day clock, as a section note since it is days, not paise). Input shape::

      "msme_ageing": {"ap_aging": {"buckets": {...}, "total_outstanding": int},
                       "msme_max_days_unpaid": int}

Exports: :func:`pack_to_csv_zip` (stdlib csv+zipfile — openpyxl is not a dependency and a
per-sheet CSV zip needs no new one) renders every figure with its badge TEXT and embeds the
integrity hash on the cover sheet; :func:`app.core.pdf.audit_pack_pdf` does the same in PDF via
the existing ReportLab machinery.

Still pending (not this ticket): Fixed Asset Register.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from typing import Any, TypedDict

from app.core.audit import canonical_json
from app.core.mahsa_coverage import badge_state
from app.core.money import Paise

SECTION_ORDER = (
    "trial_balance",
    "profit_and_loss",
    "balance_sheet",
    "general_ledger",
    "statutory_registers",
    "form_26as_reconciliation",
    "msme_ageing",
)

# WS8.1 sections not yet built (FAR needs the fixed-asset register UI/service work first).
PENDING_SECTIONS = ("fixed_asset_register",)

# Badge → artifact text. Fail-closed: anything unknown renders PENDING, never VERIFIED (§0.4).
_BADGE_TEXT = {"verified": "VERIFIED", "honest_pending": "PENDING", "blocked": "BLOCKED"}


def badge_text(state: str) -> str:
    return _BADGE_TEXT.get(state, "PENDING")


class AuditFigure(TypedDict):
    label: str
    value_paise: int
    badge: str
    evidence_ref: str


def _figure(label: str, value_paise: Any, target: str, evidence_ref: str) -> AuditFigure:
    if not isinstance(value_paise, int) or isinstance(value_paise, bool):
        raise TypeError(
            f"{label!r}: value_paise must be an exact int (paise), got "
            f"{type(value_paise).__name__}"
        )
    return {
        "label": label,
        "value_paise": value_paise,
        "badge": badge_state(target),
        "evidence_ref": evidence_ref,
    }


def _extra_figures(section_data: dict[str, Any]) -> list[AuditFigure]:
    """Optional caller-supplied figures sourced from other domains (gst/payables/payroll/tax),
    each carrying its own genuine Mahsa coverage target — see module docstring."""
    extras = section_data.get("extra_figures", [])
    return [
        _figure(item["label"], item["value_paise"], item["target"], item["evidence_ref"])
        for item in extras
    ]


def _require(entity_data: dict[str, Any], key: str) -> Any:
    if key not in entity_data:
        raise ValueError(f"entity_data missing required section: {key!r}")
    return entity_data[key]


def _trial_balance_section(entity_data: dict[str, Any]) -> list[AuditFigure]:
    tb = _require(entity_data, "trial_balance")
    ref = "ledger.trial_balance"
    return [
        _figure("Total Debit", tb["total_debit"], "ledger.trial_balance.total_debit", ref),
        _figure("Total Credit", tb["total_credit"], "ledger.trial_balance.total_credit", ref),
        _figure("Difference (must be zero)", tb["diff"], "ledger.trial_balance.diff", ref),
        *_extra_figures(tb),
    ]


def _profit_and_loss_section(entity_data: dict[str, Any]) -> list[AuditFigure]:
    pnl = _require(entity_data, "profit_and_loss")
    ref = "ledger.profit_and_loss"
    return [
        _figure("Total Income", pnl["income"], "ledger.profit_and_loss.income", ref),
        _figure("Total Expense", pnl["expense"], "ledger.profit_and_loss.expense", ref),
        _figure("Net Profit", pnl["net_profit"], "ledger.profit_and_loss.net_profit", ref),
        *_extra_figures(pnl),
    ]


def _balance_sheet_section(entity_data: dict[str, Any]) -> list[AuditFigure]:
    bs = _require(entity_data, "balance_sheet")
    ref = "ledger.balance_sheet"
    return [
        _figure("Total Assets", bs["assets"], "ledger.balance_sheet.assets", ref),
        _figure("Total Liabilities", bs["liabilities"], "ledger.balance_sheet.liabilities", ref),
        _figure("Total Equity", bs["equity"], "ledger.balance_sheet.equity", ref),
        _figure(
            "Retained Profit", bs["retained_profit"], "ledger.balance_sheet.retained_profit", ref
        ),
        *_extra_figures(bs),
    ]


def _general_ledger_section(entity_data: dict[str, Any]) -> list[AuditFigure]:
    """GL summary: one closing-balance line per account (not the full transaction detail —
    that stays behind ``evidence_ref``, fetchable via ``LedgerService.general_ledger``)."""
    accounts = _require(entity_data, "general_ledger")
    return [
        _figure(
            f"{a['code']} {a['name']} — Closing Balance",
            a["closing_balance"],
            "ledger.general_ledger.closing_balance",
            f"ledger.general_ledger:account={a['code']}",
        )
        for a in accounts
    ]


def _statutory_registers_section(entity_data: dict[str, Any]) -> list[AuditFigure]:
    """Filed statutory returns + payroll register summary — figures pulled straight from the
    rows/snapshots the domain services already produced, never recomputed here."""
    reg = _require(entity_data, "statutory_registers")
    figures: list[AuditFigure] = []
    for r in reg.get("tds_returns", []):
        head = f"TDS {r['return_type']} {r['quarter']} ({r['status']})"
        ref = "tax.file_tds_return"
        figures.append(
            _figure(
                f"{head} — Tax Deducted", r["total_deducted"],
                "tax.tds_return.total_deducted", ref,
            )
        )
        # Genuinely the late_fee_234e computation (tax_calc.late_fee_234e) → its real target.
        figures.append(
            _figure(
                f"{head} — Late Filing Fee u/s 234E", r["late_filing_fee"], "late_fee_234e", ref
            )
        )
    for r in reg.get("gst_returns", []):
        head = f"GST {r['return_type']} {r['filing_period']} ({r['status']})"
        ref = "gst.file_gstr3b"
        figures.append(
            _figure(f"{head} — Tax Payable (cash)", r["tax_payable"], "gst.return.tax_payable", ref)
        )
        # Not claimed to Mahsa on purpose (is_nil not persisted) — see GstService.recompute_claims.
        figures.append(_figure(f"{head} — Late Fee", r["late_fee"], "gst.return.late_fee", ref))
        figures.append(
            _figure(f"{head} — Interest u/s 50", r["interest"], "gst.return.interest", ref)
        )
    payroll = reg.get("payroll")
    if payroll is not None:
        ref = "payroll.build_snapshot"
        figures += [
            _figure("Payroll — Monthly Burn (gross + employer PF)", payroll["monthly_burn"],
                    "payroll.build_snapshot.monthly_burn", ref),
            _figure("Payroll — LWF Due (all states)", payroll["lwf_due_paise"],
                    "payroll.build_snapshot.lwf_due", ref),
            _figure("Payroll — Monthly Bonus Provision", payroll["monthly_bonus_required_paise"],
                    "payroll.build_snapshot.bonus_required", ref),
        ]
    return figures


def _form_26as_section(entity_data: dict[str, Any]) -> tuple[list[AuditFigure], str | None]:
    """Shape ``tax_calc.reconcile_26as`` output into per-TAN figures. ``None``/absent recon →
    honest-empty section with a note (WS7: an unwired source states that it is unwired)."""
    recon = entity_data.get("form_26as_reconciliation")
    if not recon:
        return [], (
            "No Form 26AS statement loaded — TDS-credit reconciliation pending. "
            "Nothing here is claimed reconciled."
        )
    target, ref = "tax.form_26as.reconcile", "tax.tax_calc.reconcile_26as"
    figures: list[AuditFigure] = []
    for e in recon["matched"]:
        figures.append(_figure(f"TAN {e['tan']} — TDS credit matched", e["amount"], target, ref))
    for e in recon["mismatched"]:
        figures.append(
            _figure(
                f"TAN {e['tan']} — MISMATCH variance (books − 26AS)", e["variance"], target, ref
            )
        )
    for e in recon["missing_in_26as"]:
        figures.append(
            _figure(f"TAN {e['tan']} — in books, MISSING in 26AS", e["books"], target, ref)
        )
    for e in recon["missing_in_books"]:
        figures.append(
            _figure(f"TAN {e['tan']} — in 26AS, MISSING in books", e["as_26as"], target, ref)
        )
    note = "Reconciled: all TAN-wise TDS credits match Form 26AS." if recon["reconciled"] else (
        "NOT reconciled — mismatched or one-sided TAN entries above need action."
    )
    return figures, note


def _msme_ageing_section(entity_data: dict[str, Any]) -> tuple[list[AuditFigure], str]:
    """AP ageing buckets (from ``PayablesService.ap_aging``) + the MSMED s.15 worst-case age
    (from ``msme_max_days_unpaid``) as a note — it is a day count, not paise."""
    msme = _require(entity_data, "msme_ageing")
    aging = msme["ap_aging"]
    ref = "payables.ap_aging"
    figures = [
        _figure(f"Payables outstanding — {bucket} days", value, "payables.ap_aging.bucket", ref)
        for bucket, value in aging["buckets"].items()
    ]
    figures.append(
        _figure(
            "Payables outstanding — Total", aging["total_outstanding"],
            "payables.ap_aging.total", ref,
        )
    )
    days = int(msme["msme_max_days_unpaid"])
    note = (
        f"MSMED Act s.15: oldest unpaid MSME-vendor bill is {days} days old "
        f"(45-day statutory limit{' EXCEEDED' if days > 45 else ''}). "
        "Source: payables.msme_max_days_unpaid."
    )
    return figures, note


def _integrity_header(
    sections: dict[str, list[AuditFigure]],
    *,
    rules_version: str,
    org_id: str,
    section_notes: dict[str, str],
) -> dict[str, str]:
    """Verdict-style tamper-evident seal: sha256 over the canonical JSON of every figure in
    every section (and the section notes — the MSME day-count lives there), plus the rule-pack
    version and org binding (reuses app.core.audit's primitives — no new hashing dependency,
    same construction as app.core.verdict)."""
    payload = {
        "org_id": org_id,
        "rules_version": rules_version,
        "sections": sections,
        "section_notes": section_notes,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return {"rules_version": rules_version, "org_id": org_id, "hash": digest}


def build_audit_pack(entity_data: dict[str, Any]) -> dict[str, Any]:
    """Assemble the core Audit Pack (TB/P&L/BS/GL) from already-computed domain figures.

    Every figure in every section is badged via :func:`app.core.mahsa_coverage.badge_state`
    and carries an ``evidence_ref`` back to the domain computation that produced it. The pack
    is sealed with an integrity hash so any later tampering with a figure is detectable
    (§0.4/§WS3.4 pattern).
    """
    org_id = _require(entity_data, "org_id")
    rules_version = _require(entity_data, "rules_version")
    if not org_id:
        raise ValueError("entity_data.org_id must be non-empty")

    figures_26as, note_26as = _form_26as_section(entity_data)
    figures_msme, note_msme = _msme_ageing_section(entity_data)
    sections: dict[str, list[AuditFigure]] = {
        "trial_balance": _trial_balance_section(entity_data),
        "profit_and_loss": _profit_and_loss_section(entity_data),
        "balance_sheet": _balance_sheet_section(entity_data),
        "general_ledger": _general_ledger_section(entity_data),
        "statutory_registers": _statutory_registers_section(entity_data),
        "form_26as_reconciliation": figures_26as,
        "msme_ageing": figures_msme,
    }
    section_notes: dict[str, str] = {"msme_ageing": note_msme}
    if note_26as is not None:
        section_notes["form_26as_reconciliation"] = note_26as

    return {
        "org_id": org_id,
        "rules_version": rules_version,
        "sections": sections,
        "section_notes": section_notes,
        "integrity": _integrity_header(
            sections, rules_version=rules_version, org_id=org_id, section_notes=section_notes
        ),
        # WS8.1 follow-on: Fixed Asset Register is not built by this slice.
        "pending_sections": list(PENDING_SECTIONS),
    }


def verify_pack_integrity(pack: dict[str, Any]) -> bool:
    """Recompute the seal over a pack's sections/notes and compare with the embedded hash —
    False on ANY tampered figure, note, org, or rules version. Pure; same primitive the
    artifacts embed on their cover."""
    expected = _integrity_header(
        pack["sections"],
        rules_version=pack["rules_version"],
        org_id=pack["org_id"],
        section_notes=pack["section_notes"],
    )
    return bool(pack["integrity"]["hash"] == expected["hash"])


# ---- artifact exports -----------------------------------------------------------------------


def section_title(name: str) -> str:
    return name.replace("_", " ").title().replace("Msme", "MSME").replace("26As", "26AS")


def pack_to_csv_zip(pack: dict[str, Any]) -> bytes:
    """Per-sheet CSV zip (the spreadsheet artifact — openpyxl is not a dep, stdlib does it).

    ``00_cover.csv`` embeds the pack integrity hash; every figure row carries its badge TEXT
    (VERIFIED / PENDING / BLOCKED) straight from the §0.4-gated badge on the pack — the export
    never re-decides a badge.
    """

    def _sheet(rows: list[list[str]]) -> str:
        out = io.StringIO()
        csv.writer(out).writerows(rows)
        return out.getvalue()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        integrity = pack["integrity"]
        cover = [
            ["Maisha-Mahsa Audit Pack"],
            ["Organisation", pack["org_id"]],
            ["Rules version", pack["rules_version"]],
            ["Integrity hash (SHA-256)", integrity["hash"]],
            ["Badge legend", "VERIFIED = Mahsa independently recomputed; PENDING = not yet; "
                             "BLOCKED = recompute mismatch"],
            ["Pending sections", ", ".join(pack["pending_sections"]) or "none"],
        ]
        zf.writestr("00_cover.csv", _sheet(cover))
        for i, name in enumerate(SECTION_ORDER, start=1):
            rows: list[list[str]] = [
                ["Particulars", "Amount (INR)", "Amount (paise)", "Badge", "Evidence"]
            ]
            for fig in pack["sections"][name]:
                rows.append([
                    fig["label"],
                    Paise(fig["value_paise"]).format_inr(),
                    str(fig["value_paise"]),
                    badge_text(fig["badge"]),
                    fig["evidence_ref"],
                ])
            note = pack["section_notes"].get(name)
            if note:
                rows.append(["NOTE", note, "", "", ""])
            zf.writestr(f"{i:02d}_{name}.csv", _sheet(rows))
    return buf.getvalue()
