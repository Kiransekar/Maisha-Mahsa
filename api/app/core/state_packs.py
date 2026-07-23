"""WS2.1 — state-wise compliance packs: loader, integrity check, schema validation, PT compute.

State-varying statutory data (PT slabs, LWF, S&E, minimum wages, stamp duty, e-way intra
threshold, Labour-Code rules status) lives as DATA in ``app/states/<code>.yaml``, riding the
WS1.E3 rule-pack mechanism extended per-state: ``app/states/MANIFEST.yaml`` binds a pack-set
version to one sha256 per file, and this loader refuses to serve a pack whose bytes or version
drifted — fail loud at load, never silent.

Honesty contract (§WS2.1 + §0.6):
  * ``not_applicable`` is EXPLICIT — a state with no levy renders "Not applicable in <state>",
    never a silently computed ₹0.
  * ``blocked_ca`` REFUSES to compute (raises :class:`StatePackBlocked`, message carries
    "BLOCKED-CA") — a blocked value can never leak out as zero.
  * ``sourced`` values carry ``citation_url`` + ``citation_locator`` quoting the official
    instrument verbatim; nothing numeric exists in a pack outside a ``sourced`` block.

Pure and deterministic: no clock, no network — the caller passes the month where it matters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

STATES_DIR = Path(__file__).resolve().parents[1] / "states"

#: The WS2.2 launch set. WS2.4 expansion states simply add a YAML + manifest row.
SECTIONS = (
    "pt",
    "lwf",
    "shops_establishments",
    "minimum_wages",
    "stamp_duty_share_certificates",
    "eway_intra_state_threshold",
    "labour_code_rules",
)
_STATUSES = {"sourced", "not_applicable", "blocked_ca"}


class StatePackError(RuntimeError):
    """Integrity or schema failure — the pack set is unusable and must fail loud."""


class StatePackBlocked(NotImplementedError):
    """BLOCKED-CA refusal (§0.6): the requested item has no sourced value. Subclasses
    NotImplementedError to match the repo's BLOCKED-CA convention (see tax_calc)."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_slabs(slabs: Any, where: str) -> None:
    if not isinstance(slabs, list) or not slabs:
        raise StatePackError(f"{where}: slab table must be a non-empty list")
    prev = -1
    for i, row in enumerate(slabs):
        if not isinstance(row, dict) or "tax_paise" not in row or "upto_rupees" not in row:
            raise StatePackError(f"{where}[{i}]: slab rows need upto_rupees + tax_paise")
        if not isinstance(row["tax_paise"], int) or row["tax_paise"] < 0:
            raise StatePackError(f"{where}[{i}]: tax_paise must be a non-negative int (paise)")
        feb = row.get("february_tax_paise")
        if feb is not None and (not isinstance(feb, int) or feb < 0):
            raise StatePackError(f"{where}[{i}]: february_tax_paise must be a non-negative int")
        upto = row["upto_rupees"]
        last = i == len(slabs) - 1
        if last:
            if upto is not None:
                raise StatePackError(f"{where}: final slab must be open-ended (upto_rupees null)")
        else:
            if not isinstance(upto, int) or upto <= prev:
                raise StatePackError(f"{where}[{i}]: upto_rupees must be an int, ascending")
            prev = upto


def _validate_section(code: str, name: str, sec: Any) -> None:
    if not isinstance(sec, dict) or sec.get("status") not in _STATUSES:
        raise StatePackError(f"{code}.{name}: status must be one of {sorted(_STATUSES)}")
    status = sec["status"]
    if status == "blocked_ca":
        reason = sec.get("reason") or ""
        if "BLOCKED-CA" not in reason:
            raise StatePackError(f"{code}.{name}: blocked_ca needs a reason carrying BLOCKED-CA")
        return
    if status == "not_applicable":
        if not sec.get("basis"):
            raise StatePackError(f"{code}.{name}: not_applicable needs a basis")
        return
    # sourced — the only status allowed to carry numbers, and it must cite the instrument.
    url = str(sec.get("citation_url") or "")
    if not url.startswith("http") or not sec.get("citation_locator"):
        raise StatePackError(
            f"{code}.{name}: sourced needs citation_url (resolvable) + citation_locator (§0.6)"
        )
    if name == "pt":
        if sec.get("periodicity") not in {"monthly", "half_yearly"}:
            raise StatePackError(f"{code}.pt: periodicity must be monthly|half_yearly")
        if sec["periodicity"] == "monthly":
            tables = sec.get("slabs_monthly")
            if not isinstance(tables, dict) or not tables:
                raise StatePackError(f"{code}.pt: monthly PT needs slabs_monthly tables")
            for cat, slabs in tables.items():
                _validate_slabs(slabs, f"{code}.pt.slabs_monthly.{cat}")
        else:
            tables = sec.get("slabs_half_yearly")
            if not isinstance(tables, dict) or not tables:
                raise StatePackError(f"{code}.pt: half-yearly PT needs slabs_half_yearly tables")
            for jur, slabs in tables.items():
                if isinstance(slabs, dict):  # a jurisdiction may itself be BLOCKED-CA
                    if slabs.get("status") != "blocked_ca" or "BLOCKED-CA" not in str(
                        slabs.get("reason") or ""
                    ):
                        raise StatePackError(
                            f"{code}.pt.slabs_half_yearly.{jur}: dict form must be a "
                            f"blocked_ca marker with a BLOCKED-CA reason"
                        )
                else:
                    _validate_slabs(slabs, f"{code}.pt.slabs_half_yearly.{jur}")


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict[str, Any]]:
    """Load MANIFEST + every pack, verifying sha256 and version. Cached for the process —
    packs are immutable data; a new pack set is a new deploy."""
    return load_pack_set(STATES_DIR)


def load_pack_set(states_dir: Path) -> dict[str, dict[str, Any]]:
    """Uncached load of a pack directory (tests point this at tampered copies)."""
    manifest_path = states_dir / "MANIFEST.yaml"
    if not manifest_path.exists():
        raise StatePackError(f"state-pack manifest missing: {manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text())
    version = manifest.get("version")
    files = manifest.get("files")
    if not version or not isinstance(files, dict) or not files:
        raise StatePackError("state-pack MANIFEST.yaml needs version + files map")
    packs: dict[str, dict[str, Any]] = {}
    for fname, want_sha in files.items():
        path = states_dir / fname
        if not path.exists():
            raise StatePackError(f"state pack listed in manifest but missing: {fname}")
        got = _sha256(path)
        if got != want_sha:
            raise StatePackError(
                f"state pack {fname} sha256 mismatch: manifest {want_sha}, file {got} — "
                f"refusing to serve a drifted pack (WS1.E3 mechanism)"
            )
        pack = yaml.safe_load(path.read_text())
        code = pack.get("code")
        if not code or f"{code}.yaml" != fname:
            raise StatePackError(f"{fname}: pack code {code!r} does not match its filename")
        if pack.get("pack_version") != version:
            raise StatePackError(
                f"{fname}: pack_version {pack.get('pack_version')!r} != manifest {version!r}"
            )
        for name in SECTIONS:
            _validate_section(code, name, pack.get(name))
        pack["_manifest_version"] = version
        pack["_sha256"] = got
        packs[code] = pack
    return packs


def get_pack(state: str | None) -> dict[str, Any] | None:
    """The verified pack for ``state`` (case-insensitive), or None when no pack exists yet
    (WS2.4 expansion states)."""
    return _load_all().get((state or "").upper())


# ── PT determinations ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PtDetermination:
    """One honest PT answer. ``status``:
    * ``computed``       — amount_paise holds the cited figure
    * ``not_applicable`` — no levy exists in this state (amount None, never a fake 0)
    * ``half_yearly``    — the state levies half-yearly; use :func:`pt_half_yearly`
    * ``no_pack``        — state not yet covered by a pack (WS2.4 backlog)
    """

    state: str
    status: str
    amount_paise: int | None = None
    citation_url: str | None = None
    citation_locator: str | None = None
    pack_version: str | None = None
    note: str | None = None


def _walk(slabs: list[dict[str, Any]], income_rupees: int, month: int) -> int:
    for row in slabs:
        upto = row["upto_rupees"]
        if upto is None or income_rupees <= upto:
            feb = row.get("february_tax_paise")
            return int(feb) if month == 2 and feb is not None else int(row["tax_paise"])
    raise StatePackError("slab table had no open-ended final row")  # unreachable post-validate


def pt_status(state: str | None) -> str:
    """monthly | half_yearly | not_applicable | blocked | no_pack — for callers that only
    need applicability (e.g. ``pt_is_modelled``)."""
    pack = get_pack(state)
    if pack is None:
        return "no_pack"
    pt = pack["pt"]
    if pt["status"] == "not_applicable":
        return "not_applicable"
    if pt["status"] == "blocked_ca":
        return "blocked"
    return str(pt["periodicity"])


def pt_monthly(
    state: str | None, gross_monthly_paise: int, month: int, category: str = "male"
) -> PtDetermination:
    """Monthly-payslip PT determination. ``month`` is 1–12 (February specials). ``category``
    selects the slab table where the instrument distinguishes (MH men/women); packs with a
    single table use key ``all``. Raises :class:`StatePackBlocked` when the state's PT is
    BLOCKED-CA — refusal, never zero."""
    code = (state or "").upper()
    pack = get_pack(code)
    if pack is None:
        return PtDetermination(
            state=code,
            status="no_pack",
            note="state not yet covered by a WS2 pack (expansion backlog)",
        )
    pt = pack["pt"]
    version = pack["_manifest_version"]
    if pt["status"] == "not_applicable":
        return PtDetermination(
            state=code, status="not_applicable", pack_version=version, note=pt["basis"]
        )
    if pt["status"] == "blocked_ca":
        raise StatePackBlocked(pt["reason"])
    if pt["periodicity"] == "half_yearly":
        return PtDetermination(
            state=code,
            status="half_yearly",
            pack_version=version,
            citation_url=pt["citation_url"],
            citation_locator=pt["citation_locator"],
            note="PT here is a half-yearly local-body levy, not a monthly payslip deduction; "
            "compute it with pt_half_yearly per jurisdiction.",
        )
    tables = pt["slabs_monthly"]
    slabs = tables.get(category) or tables.get("all")
    if slabs is None:
        raise StatePackError(f"{code}.pt: no slab table for category {category!r}")
    amount = _walk(slabs, int(gross_monthly_paise) // 100, int(month))
    return PtDetermination(
        state=code,
        status="computed",
        amount_paise=amount,
        pack_version=version,
        citation_url=pt["citation_url"],
        citation_locator=pt["citation_locator"],
    )


def pt_half_yearly(
    state: str | None, half_yearly_income_paise: int, jurisdiction: str
) -> PtDetermination:
    """Half-yearly PT for a half-yearly state (TN), per local-body jurisdiction. Raises
    :class:`StatePackBlocked` for a BLOCKED-CA jurisdiction (e.g. Madurai Corporation) and
    ValueError for an unknown one."""
    code = (state or "").upper()
    pack = get_pack(code)
    if pack is None:
        raise ValueError(f"no state pack for {code!r}")
    pt = pack["pt"]
    if pt["status"] == "blocked_ca":
        raise StatePackBlocked(pt["reason"])
    if pt["status"] != "sourced" or pt.get("periodicity") != "half_yearly":
        raise ValueError(f"{code} PT is not a half-yearly levy (status={pt_status(code)})")
    tables = pt["slabs_half_yearly"]
    slabs = tables.get(jurisdiction)
    if slabs is None:
        raise ValueError(
            f"unknown {code} PT jurisdiction {jurisdiction!r}; known: {sorted(tables)}"
        )
    if isinstance(slabs, dict):  # blocked_ca marker (validated at load)
        raise StatePackBlocked(slabs["reason"])
    # month=0: half-yearly tables have no February special.
    amount = _walk(slabs, int(half_yearly_income_paise) // 100, 0)
    return PtDetermination(
        state=code,
        status="computed",
        amount_paise=amount,
        pack_version=pack["_manifest_version"],
        citation_url=pt["citation_url"],
        citation_locator=pt["citation_locator"],
        note=f"half-yearly levy, jurisdiction {jurisdiction}",
    )


def pt_provenance(state: str | None) -> dict[str, Any]:
    """Provenance card for UI/API surfacing (WS2.3): status + citation + pack integrity info.
    Never raises for blocked — the card REPORTS blocked so the surface can render the refusal."""
    code = (state or "").upper()
    pack = get_pack(code)
    if pack is None:
        return {"state": code, "pt_status": "no_pack", "pack_version": None}
    pt = pack["pt"]
    out: dict[str, Any] = {
        "state": code,
        "pt_status": pt_status(code),
        "pack_version": pack["_manifest_version"],
        "pack_sha256": pack["_sha256"],
    }
    if pt["status"] == "sourced":
        out["statute"] = pt["statute"]
        out["section"] = pt["section"]
        out["citation_url"] = pt["citation_url"]
        out["citation_locator"] = pt["citation_locator"]
        if pt["periodicity"] == "half_yearly":
            tables = pt["slabs_half_yearly"]
            out["jurisdictions"] = sorted(tables)
            out["blocked_jurisdictions"] = sorted(
                j for j, s in tables.items() if isinstance(s, dict)
            )
    elif pt["status"] == "not_applicable":
        out["note"] = pt["basis"]
    else:
        out["blocked_reason"] = pt["reason"]
    return out
