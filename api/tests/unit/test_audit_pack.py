"""WS8.1 core slice — Audit Pack generator tests.

These must be *able to fail*: each proves a real contract (section shape, honest badging,
tamper-evidence), not a vacuous assert.
"""

from __future__ import annotations

import copy

import pytest

from app.core.audit_pack import SECTION_ORDER, build_audit_pack

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
    "general_ledger": [
        {"code": "1000", "name": "Cash", "closing_balance": 800_000},
        {"code": "3000", "name": "Capital", "closing_balance": 480_000},
    ],
}


def test_pack_has_the_four_core_sections() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    assert set(pack["sections"]) == set(SECTION_ORDER)
    for name in SECTION_ORDER:
        figures = pack["sections"][name]
        assert len(figures) > 0, name
        for fig in figures:
            assert set(fig) == {"label", "value_paise", "badge", "evidence_ref"}
            assert isinstance(fig["value_paise"], int)
            assert fig["badge"] in ("verified", "honest_pending")
            assert fig["evidence_ref"]


def test_ledger_bookkeeping_figures_are_honest_pending_not_verified() -> None:
    # Ledger has no Mahsa sub-vector (see app/domains/ledger/service.py docstring) — raw
    # bookkeeping totals are never fabricated as verified.
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    tb_diff = next(
        f for f in pack["sections"]["trial_balance"] if f["label"] == "Difference (must be zero)"
    )
    assert tb_diff["badge"] == "honest_pending"
    for fig in pack["sections"]["general_ledger"]:
        assert fig["badge"] == "honest_pending"


def test_extra_figure_with_a_ported_target_is_verified() -> None:
    # "esi" is a real, Mahsa-ported oracle target (dif/tests/parity.rs PORTED) — a genuinely
    # statutory-sourced figure supplied under that target must badge verified.
    data = copy.deepcopy(ENTITY_DATA)
    data["balance_sheet"]["extra_figures"] = [
        {
            "label": "ESI Payable (employer+employee)",
            "value_paise": 65_100,
            "target": "esi",
            "evidence_ref": "payroll.build_snapshot:esi",
        }
    ]
    pack = build_audit_pack(data)
    esi_fig = next(
        f for f in pack["sections"]["balance_sheet"] if f["label"].startswith("ESI Payable")
    )
    assert esi_fig["badge"] == "verified"


def test_extra_figure_with_an_unported_target_is_honest_pending() -> None:
    data = copy.deepcopy(ENTITY_DATA)
    data["profit_and_loss"]["extra_figures"] = [
        {
            "label": "Estimated ITR liability",
            "value_paise": 10_000,
            "target": "itr_computation",  # known unported (see test_mahsa_coverage.py)
            "evidence_ref": "tax.itr_computation",
        }
    ]
    pack = build_audit_pack(data)
    fig = next(
        f for f in pack["sections"]["profit_and_loss"] if f["label"] == "Estimated ITR liability"
    )
    assert fig["badge"] == "honest_pending"


def test_integrity_hash_is_deterministic() -> None:
    a = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    b = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    assert a["integrity"]["hash"] == b["integrity"]["hash"]


def test_integrity_hash_changes_when_a_figure_changes() -> None:
    base = build_audit_pack(copy.deepcopy(ENTITY_DATA))

    tampered = copy.deepcopy(ENTITY_DATA)
    tampered["trial_balance"]["total_debit"] += 1
    changed = build_audit_pack(tampered)

    assert changed["integrity"]["hash"] != base["integrity"]["hash"]


def test_integrity_hash_changes_when_a_gl_account_balance_changes() -> None:
    base = build_audit_pack(copy.deepcopy(ENTITY_DATA))

    tampered = copy.deepcopy(ENTITY_DATA)
    tampered["general_ledger"][0]["closing_balance"] += 100

    changed = build_audit_pack(tampered)
    assert changed["integrity"]["hash"] != base["integrity"]["hash"]


def test_missing_section_raises() -> None:
    data = copy.deepcopy(ENTITY_DATA)
    del data["balance_sheet"]
    with pytest.raises(ValueError, match="balance_sheet"):
        build_audit_pack(data)


def test_empty_org_id_raises() -> None:
    data = copy.deepcopy(ENTITY_DATA)
    data["org_id"] = ""
    with pytest.raises(ValueError, match="org_id"):
        build_audit_pack(data)


def test_non_int_value_paise_raises() -> None:
    data = copy.deepcopy(ENTITY_DATA)
    data["profit_and_loss"]["income"] = 3000.0  # float money is forbidden (CLAUDE.md §7)
    with pytest.raises(TypeError, match="value_paise"):
        build_audit_pack(data)


def test_pending_sections_are_named_not_silently_dropped() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    for section in ("fixed_asset_register", "statutory_registers", "msme_ageing"):
        assert section in pack["pending_sections"]
