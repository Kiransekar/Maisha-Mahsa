"""WS8.1 core slice — Audit Pack generator tests.

These must be *able to fail*: each proves a real contract (section shape, honest badging,
tamper-evidence), not a vacuous assert.
"""

from __future__ import annotations

import base64
import copy
import csv
import io
import re
import zipfile
import zlib

import pytest

from app.core.audit_pack import (
    SECTION_ORDER,
    build_audit_pack,
    pack_to_csv_zip,
    verify_pack_integrity,
)
from app.core.pdf import audit_pack_pdf
from app.domains.tax.tax_calc import reconcile_26as

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
    "statutory_registers": {
        "tds_returns": [
            {
                "return_type": "24Q", "quarter": "2026-Q1", "status": "filed",
                "total_deducted": 250_000, "late_filing_fee": 40_000,
            }
        ],
        "gst_returns": [
            {
                "return_type": "GSTR-3B", "filing_period": "2026-06", "status": "filed",
                "tax_payable": 90_000, "late_fee": 5_000, "interest": 1_200,
            }
        ],
        "payroll": {
            "monthly_burn": 1_200_000,
            "lwf_due_paise": 4_000,
            "monthly_bonus_required_paise": 83_300,
        },
    },
    # Default: no 26AS statement loaded — the section must be honest-empty, never "reconciled".
    "form_26as_reconciliation": None,
    "msme_ageing": {
        "ap_aging": {
            "buckets": {"0-30": 100_000, "31-60": 0, "61-90": 20_000, "90+": 0},
            "total_outstanding": 120_000,
        },
        "msme_max_days_unpaid": 52,
    },
}


def test_pack_has_every_ws81_section() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    assert set(pack["sections"]) == set(SECTION_ORDER)
    for name in SECTION_ORDER:
        figures = pack["sections"][name]
        if name == "form_26as_reconciliation":
            # honest-empty: no 26AS statement in the default data → no figures, but a note.
            assert figures == []
            assert "No Form 26AS statement loaded" in pack["section_notes"][name]
            continue
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


def test_pending_sections_now_only_the_fixed_asset_register() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    assert pack["pending_sections"] == ["fixed_asset_register"]


# ---- WS8.1 remainder: statutory registers / 26AS / MSME -------------------------------------


def test_tds_late_fee_is_verified_but_deducted_total_is_pending() -> None:
    # late_filing_fee genuinely IS tax_calc.late_fee_234e (a Mahsa-ported target) → verified.
    # total_deducted is an aggregate with no oracle target → must stay honest_pending.
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    regs = pack["sections"]["statutory_registers"]
    late_fee = next(f for f in regs if "Late Filing Fee u/s 234E" in f["label"])
    deducted = next(f for f in regs if "Tax Deducted" in f["label"])
    assert late_fee["badge"] == "verified"
    assert deducted["badge"] == "honest_pending"


def test_gst_register_figures_are_never_verified() -> None:
    # GstService.recompute_claims deliberately does not claim late_fee (is_nil unpersisted) and
    # interest_3b is not a coverage target — none of these may fabricate a verified badge.
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    gst_figs = [f for f in pack["sections"]["statutory_registers"] if f["label"].startswith("GST ")]
    assert len(gst_figs) == 3
    assert all(f["badge"] == "honest_pending" for f in gst_figs)


def test_26as_section_reuses_reconcile_output_per_tan() -> None:
    data = copy.deepcopy(ENTITY_DATA)
    data["form_26as_reconciliation"] = reconcile_26as(
        books=[{"tan": "BLRA00001A", "amount": 10_000}, {"tan": "BLRB00002B", "amount": 5_000}],
        as_26as=[{"tan": "BLRA00001A", "amount": 10_000}, {"tan": "BLRB00002B", "amount": 4_000}],
    )
    pack = build_audit_pack(data)
    figs = pack["sections"]["form_26as_reconciliation"]
    matched = next(f for f in figs if "BLRA00001A" in f["label"] and "matched" in f["label"])
    variance = next(f for f in figs if "BLRB00002B" in f["label"] and "MISMATCH" in f["label"])
    assert matched["value_paise"] == 10_000
    assert variance["value_paise"] == 1_000  # books − 26AS
    # No oracle target exists for the recon → nothing here may read verified (§0.4).
    assert all(f["badge"] == "honest_pending" for f in figs)
    assert "NOT reconciled" in pack["section_notes"]["form_26as_reconciliation"]


def test_msme_section_has_buckets_total_and_s15_note() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    figs = pack["sections"]["msme_ageing"]
    labels = [f["label"] for f in figs]
    assert "Payables outstanding — 61-90 days" in labels
    total = next(f for f in figs if f["label"] == "Payables outstanding — Total")
    assert total["value_paise"] == 120_000
    note = pack["section_notes"]["msme_ageing"]
    assert "52 days" in note
    assert "EXCEEDED" in note  # 52 > the 45-day s.15 limit


# ---- artifacts: CSV-zip + PDF ----------------------------------------------------------------


def _zip_sheets(blob: bytes) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return {
            name: list(csv.reader(io.StringIO(zf.read(name).decode("utf-8"))))
            for name in zf.namelist()
        }


def test_zip_artifact_embeds_integrity_hash_and_honest_badge_text() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    sheets = _zip_sheets(pack_to_csv_zip(pack))
    # one sheet per section + the cover
    assert len(sheets) == len(SECTION_ORDER) + 1
    cover = sheets["00_cover.csv"]
    assert ["Integrity hash (SHA-256)", pack["integrity"]["hash"]] in cover
    reg = sheets["05_statutory_registers.csv"]
    by_label = {row[0]: row for row in reg[1:] if row[0] != "NOTE"}
    # A Mahsa-recomputed figure reads VERIFIED; an unported one must NOT.
    assert by_label["TDS 24Q 2026-Q1 (filed) — Late Filing Fee u/s 234E"][3] == "VERIFIED"
    assert by_label["TDS 24Q 2026-Q1 (filed) — Tax Deducted"][3] == "PENDING"
    assert by_label["GST GSTR-3B 2026-06 (filed) — Interest u/s 50"][3] == "PENDING"
    # MSME note (with the s.15 day count) survives into the artifact.
    msme = sheets["07_msme_ageing.csv"]
    assert any(row[0] == "NOTE" and "52 days" in row[1] for row in msme)


def test_integrity_verification_detects_a_tampered_artifact() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    assert verify_pack_integrity(pack) is True

    tampered_figure = copy.deepcopy(pack)
    tampered_figure["sections"]["trial_balance"][0]["value_paise"] += 1
    assert verify_pack_integrity(tampered_figure) is False

    tampered_badge = copy.deepcopy(pack)
    tampered_badge["sections"]["statutory_registers"][0]["badge"] = "verified"
    assert verify_pack_integrity(tampered_badge) is False

    tampered_note = copy.deepcopy(pack)
    tampered_note["section_notes"]["msme_ageing"] = "all fine"
    assert verify_pack_integrity(tampered_note) is False


def _pdf_text(blob: bytes) -> bytes:
    """Concatenate the decoded content streams of a ReportLab PDF (enough to grep literals).
    ReportLab emits ASCII85-wrapped Flate streams; fall back through the encodings."""
    out = b""
    for body in re.findall(rb"stream\r?\n(.*?)endstream", blob, re.DOTALL):
        body = body.strip(b"\r\n")
        for decode in (
            lambda b: zlib.decompress(base64.a85decode(b.rstrip(b"~>"))),
            zlib.decompress,
            lambda b: b,
        ):
            try:
                out += decode(body)
                break
            except Exception:  # noqa: BLE001 - try the next encoding
                continue
    return out


def test_pdf_artifact_embeds_hash_and_badge_text() -> None:
    pack = build_audit_pack(copy.deepcopy(ENTITY_DATA))
    blob = audit_pack_pdf(pack)
    assert blob.startswith(b"%PDF")
    text = _pdf_text(blob)
    assert pack["integrity"]["hash"][:16].encode() in text
    assert b"VERIFIED" in text  # the 234E late fee row
    assert b"PENDING" in text  # every unported figure
