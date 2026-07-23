"""Statutory regime selector — Income-tax Act 1961 ↔ Income-tax Act 2025 (MMX-1.0 §WS1.A1).

The 2025 Act takes effect for events on or after **2026-04-01**. Whether a TDS/TCS event falls
under the old or new regime is keyed on the **earlier of the credit date or the payment date**
(the same trigger the Act uses for deduction timing). Everything statutory downstream — section
citations, form names, "Tax Year" labelling — is looked up *through* the resolved regime, never
hardcoded (see the §WS1.A2 citation sweep).

Only structure that is explicitly enumerated in the spec lives here. The 2025 payment-code table
(1001–1067) is a data pack whose individual codes are BLOCKED-CA until sourced (§0.6); this module
exposes the loader shape but ships no invented codes.

Pure & deterministic: the caller supplies the dates; nothing here reads a clock.
"""

from __future__ import annotations

from datetime import date

REGIME_1961 = "regime_1961"
REGIME_2025 = "regime_2025"

# The 2025 Act applies to events on/after this date (start of Tax Year 2026-27).
REGIME_BOUNDARY = date(2026, 4, 1)


def trigger_date(credit_date: date | None, payment_date: date | None) -> date:
    """The date that decides the regime: the **earlier** of credit and payment (§WS1.A1).
    At least one must be given."""
    dates = [d for d in (credit_date, payment_date) if d is not None]
    if not dates:
        raise ValueError("regime resolution needs a credit date, a payment date, or both")
    return min(dates)


def regime_for(credit_date: date | None = None, payment_date: date | None = None) -> str:
    """Resolve the governing regime for a TDS/TCS event from its credit/payment dates.
    Earlier-of-credit-or-payment < 2026-04-01 → 1961, else 2025."""
    return REGIME_1961 if trigger_date(credit_date, payment_date) < REGIME_BOUNDARY else REGIME_2025


# ---- Form map (1961 → 2025), explicitly enumerated in §WS1.A1 --------------------------
# key -> {regime: form name}. The 2025 names come straight from the spec's mapping:
#   16→130, 16A→131, 24Q→138, 3CD→26, 15G/H→121.
_FORMS: dict[str, dict[str, str]] = {
    "tds_salary_certificate": {REGIME_1961: "Form 16", REGIME_2025: "Form 130"},
    "tds_other_certificate": {REGIME_1961: "Form 16A", REGIME_2025: "Form 131"},
    "tds_salary_return": {REGIME_1961: "Form 24Q", REGIME_2025: "Form 138"},
    "tax_audit_report": {REGIME_1961: "Form 3CD", REGIME_2025: "Form 26"},
    "no_tds_declaration": {REGIME_1961: "Form 15G/15H", REGIME_2025: "Form 121"},
}


def form_name(key: str, regime: str) -> str:
    """Regime-aware statutory form name. Raises on an unknown key so a missing mapping is a
    hard failure, never a silent wrong form."""
    try:
        return _FORMS[key][regime]
    except KeyError as e:
        raise KeyError(f"no form mapping for key={key!r} regime={regime!r}") from e


def year_label(regime: str) -> str:
    """The period noun each regime uses: 1961 says 'Assessment Year', 2025 says 'Tax Year'."""
    return "Tax Year" if regime == REGIME_2025 else "Assessment Year"


# ---- 2025 payment-code table (s.392–394) — BLOCKED-CA data pack -------------------------
# The 2025 Act replaces the 194x section labels with numeric payment codes in the 1001–1067
# range. Individual codes are statutory values → they enter only from a CA-initialled pack
# (§0.6). Until then this stays empty; callers must handle absence, never guess a code.
_PAYMENT_CODES_2025: dict[str, int] = {}


def payment_code_2025(nature: str) -> int | None:
    """The 2025 payment code for a nature of payment, or None if not yet sourced (BLOCKED-CA)."""
    return _PAYMENT_CODES_2025.get(nature)
