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

**Explicitly out of scope for this ticket** (follow-on): Excel/PDF rendering, Fixed Asset
Register, statutory registers, GST↔26AS reconciliation, and MSME ageing sections. This module
returns the structured pack only; see ``pack["pending_sections"]``.
"""

from __future__ import annotations

import hashlib
from typing import Any, TypedDict

from app.core.audit import canonical_json
from app.core.mahsa_coverage import badge_state

SECTION_ORDER = ("trial_balance", "profit_and_loss", "balance_sheet", "general_ledger")

# Follow-on sections named in WS8.1 that this core slice does not yet build.
PENDING_SECTIONS = (
    "fixed_asset_register",
    "statutory_registers",
    "gst_26as_reconciliation",
    "msme_ageing",
)


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


def _integrity_header(
    sections: dict[str, list[AuditFigure]], *, rules_version: str, org_id: str
) -> dict[str, str]:
    """Verdict-style tamper-evident seal: sha256 over the canonical JSON of every figure in
    every section, plus the rule-pack version and org binding (reuses app.core.audit's
    primitives — no new hashing dependency, same construction as app.core.verdict)."""
    payload = {"org_id": org_id, "rules_version": rules_version, "sections": sections}
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

    sections: dict[str, list[AuditFigure]] = {
        "trial_balance": _trial_balance_section(entity_data),
        "profit_and_loss": _profit_and_loss_section(entity_data),
        "balance_sheet": _balance_sheet_section(entity_data),
        "general_ledger": _general_ledger_section(entity_data),
    }

    return {
        "org_id": org_id,
        "rules_version": rules_version,
        "sections": sections,
        "integrity": _integrity_header(sections, rules_version=rules_version, org_id=org_id),
        # WS8.1 follow-on: Excel/PDF rendering + these fuller sections, not built by this slice.
        "pending_sections": list(PENDING_SECTIONS),
    }
