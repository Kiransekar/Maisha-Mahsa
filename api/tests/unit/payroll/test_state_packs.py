"""WS2.1 state-pack framework tests: manifest integrity, schema validation, applicability
resolution, not-applicable honesty, and BLOCKED-CA refusal (never a silent ₹0)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core import state_packs
from app.core.state_packs import (
    STATES_DIR,
    StatePackBlocked,
    StatePackError,
    load_pack_set,
    pt_half_yearly,
    pt_monthly,
    pt_provenance,
    pt_status,
)
from app.domains.payroll import statutory

# ── integrity (the WS1.E3 mechanism, extended per-state) ─────────────────────────────────


def test_shipped_pack_set_loads_verified() -> None:
    packs = load_pack_set(STATES_DIR)
    assert set(packs) == {"MH", "KA", "TN", "TS", "AP", "GJ", "WB", "DL", "HR", "UP"}
    for pack in packs.values():
        assert pack["_manifest_version"] == "2026.07.1"


def _copy_packs(tmp_path: Path) -> Path:
    dst = tmp_path / "states"
    shutil.copytree(STATES_DIR, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def test_tampered_pack_bytes_refused(tmp_path: Path) -> None:
    dst = _copy_packs(tmp_path)
    mh = dst / "MH.yaml"
    # Flip one statutory figure: Rs.175 -> Rs.174. The manifest sha256 must catch it.
    mh.write_text(mh.read_text().replace("tax_paise: 17500", "tax_paise: 17400"))
    with pytest.raises(StatePackError, match="sha256 mismatch"):
        load_pack_set(dst)


def test_missing_listed_pack_refused(tmp_path: Path) -> None:
    dst = _copy_packs(tmp_path)
    (dst / "KA.yaml").unlink()
    with pytest.raises(StatePackError, match="missing"):
        load_pack_set(dst)


def test_version_drift_refused(tmp_path: Path) -> None:
    dst = _copy_packs(tmp_path)
    man = dst / "MANIFEST.yaml"
    man.write_text(man.read_text().replace('version: "2026.07.1"', 'version: "2026.07.9"'))
    with pytest.raises(StatePackError, match="pack_version"):
        load_pack_set(dst)


# ── schema validation ────────────────────────────────────────────────────────────────────


def test_blocked_section_without_marker_rejected() -> None:
    with pytest.raises(StatePackError, match="BLOCKED-CA"):
        state_packs._validate_section("XX", "lwf", {"status": "blocked_ca", "reason": "todo"})


def test_sourced_section_without_citation_rejected() -> None:
    with pytest.raises(StatePackError, match="citation_url"):
        state_packs._validate_section("XX", "lwf", {"status": "sourced", "reason": "x"})


def test_slab_table_must_end_open_ended() -> None:
    with pytest.raises(StatePackError, match="open-ended"):
        state_packs._validate_slabs([{"upto_rupees": 100, "tax_paise": 0}], "XX")


# ── applicability resolution + honesty ───────────────────────────────────────────────────


def test_not_applicable_is_explicit_never_a_computed_zero() -> None:
    for code in ("DL", "HR", "UP"):
        det = pt_monthly(code, 5_000_000, 6)
        assert det.status == "not_applicable"
        assert det.amount_paise is None  # no fake 0 — the payslip line derives its nil openly
        assert "Not applicable" in (det.note or "")
        assert pt_provenance(code)["pt_status"] == "not_applicable"


def test_half_yearly_state_reports_half_yearly_not_zero() -> None:
    det = pt_monthly("TN", 5_000_000, 6)
    assert det.status == "half_yearly" and det.amount_paise is None
    assert pt_status("TN") == "half_yearly"


def test_unknown_state_is_no_pack() -> None:
    det = pt_monthly("KL", 5_000_000, 6)
    assert det.status == "no_pack" and det.amount_paise is None
    assert pt_status("KL") == "no_pack"


def test_blocked_jurisdiction_refuses_never_zero() -> None:
    with pytest.raises(StatePackBlocked, match="BLOCKED-CA"):
        pt_half_yearly("TN", 5_000_000, "madurai_corporation")


def test_unknown_jurisdiction_is_an_error_not_zero() -> None:
    with pytest.raises(ValueError, match="jurisdiction"):
        pt_half_yearly("TN", 5_000_000, "coimbatore_corporation")


# ── cited figures through the pack path ──────────────────────────────────────────────────


def test_ka_february_special_from_act_33_of_2025() -> None:
    # The pre-pack in-code table missed this: KA charges Rs.300 in February since 01.04.2025.
    assert pt_monthly("KA", 2_500_000, 2).amount_paise == 30000
    assert pt_monthly("KA", 2_500_000, 6).amount_paise == 20000


def test_mh_women_table_exists_in_pack_data() -> None:
    # The instrument distinguishes men/women; the engine defaults to the men's table (a
    # documented gap), but the pack carries both so the wiring is data-ready.
    assert pt_monthly("MH", 2_000_000, 6, category="female").amount_paise == 0
    assert pt_monthly("MH", 2_000_000, 6, category="male").amount_paise == 20000
    assert pt_monthly("MH", 2_600_000, 6, category="female").amount_paise == 20000


def test_statutory_professional_tax_routes_through_pack() -> None:
    # The single shared payroll entrypoint now computes from pack data.
    assert int(statutory.professional_tax("MH", 2_000_000, 2)) == 30000
    assert int(statutory.professional_tax("KA", 2_500_000, 2)) == 30000  # pack fix visible here
    assert int(statutory.professional_tax("DL", 2_000_000, 6)) == 0
    assert statutory.pt_is_modelled("MH") and not statutory.pt_is_modelled("TN")
    assert not statutory.pt_is_modelled("DL")


def test_provenance_card_carries_citation_and_integrity() -> None:
    card = pt_provenance("MH")
    assert card["pt_status"] == "monthly"
    assert card["citation_url"].startswith("https://www.mahagst.gov.in/")
    assert "SCHEDULE I" in card["citation_locator"]
    assert card["pack_version"] == "2026.07.1" and len(card["pack_sha256"]) == 64
    tn = pt_provenance("TN")
    assert tn["blocked_jurisdictions"] == ["madurai_corporation"]
