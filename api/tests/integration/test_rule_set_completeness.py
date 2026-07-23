"""P4-RULES: the CA-signed rule set (dif/rules/rules.yaml) and the per-domain rules.py owners
stay in lock-step — no orphan rule IDs either way, and every rule cites a statute + section."""

from __future__ import annotations

import hashlib
import importlib
import pkgutil
from pathlib import Path

import yaml

import app.domains as domains_pkg

RULES_YAML = Path(__file__).resolve().parents[2].parent / "dif" / "rules" / "rules.yaml"


def _yaml_rules() -> list[dict]:
    data = yaml.safe_load(RULES_YAML.read_text())
    return data["rules"]


def _python_rule_ids() -> set[str]:
    ids: set[str] = set()
    for mod in pkgutil.iter_modules(domains_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            rules_mod = importlib.import_module(f"app.domains.{mod.name}.rules")
        except ModuleNotFoundError:
            continue
        for attr in dir(rules_mod):
            value = getattr(rules_mod, attr)
            if attr.endswith("_RULES") and isinstance(value, dict):
                ids.update(value.keys())
    return ids


def test_python_and_yaml_rule_ids_match_exactly():
    yaml_ids = {r["id"] for r in _yaml_rules()}
    py_ids = _python_rule_ids()
    assert py_ids, "no Python rule IDs discovered"
    assert py_ids == yaml_ids, (
        f"rule-set drift — in Python only: {py_ids - yaml_ids}; in YAML only: {yaml_ids - py_ids}"
    )


def test_every_rule_cites_statute_and_section():
    for rule in _yaml_rules():
        for field in ("id", "domain", "statute", "section", "severity"):
            assert rule.get(field), f"rule {rule.get('id')} missing '{field}'"


# ---- WS1.B4: Labour-Code citation convention ------------------------------------------

# Acts repealed by CoW 2019 s.69(1) / CoSS 2020 s.164(1) (both read verbatim from the India
# Code PDFs already cited by tests/statutory_oracle/vectors/ws1b_*.yaml). A repealed Act may
# appear in a citation only alongside its successor Code ("(ex ...)" trace / savings clause),
# never as the sole authority.
_REPEALED_LABOUR_ACTS = (
    "EPF & MP Act",
    "Employees' Provident Funds and Miscellaneous",
    "ESI Act",
    "Employees' State Insurance Act",
    "Payment of Bonus Act",
    "Payment of Gratuity Act",
    "Payment of Wages Act",
)
_CODE_MARKERS = ("Code on Wages", "Code on Social Security", "CoSS", "ex ")


def test_no_repealed_labour_act_cited_as_primary_statute():
    for rule in _yaml_rules():
        statute = rule["statute"]
        for act in _REPEALED_LABOUR_ACTS:
            assert act not in statute, (
                f"rule {rule['id']}: statute field cites repealed '{act}' as primary — "
                f"cite the successor Code with an '(ex ...)' trace (WS1.B4 convention)"
            )
        # A repealed Act in section/action text must ride with a Code marker on that field.
        for field in ("section", "action"):
            text = rule.get(field, "")
            if any(act in text for act in _REPEALED_LABOUR_ACTS):
                assert any(marker in text for marker in _CODE_MARKERS), (
                    f"rule {rule['id']}: '{field}' names a repealed labour Act with no "
                    f"successor-Code trace: {text!r}"
                )


# ---- WS1.E3: pack manifest, changelog, archive ----------------------------------------

PACK_DIR = RULES_YAML.parent


def _manifest() -> dict:
    return yaml.safe_load((PACK_DIR / "MANIFEST.yaml").read_text())


def test_manifest_sha256_and_version_match_the_pack():
    manifest = _manifest()
    digest = hashlib.sha256(RULES_YAML.read_bytes()).hexdigest()
    assert manifest["rules_sha256"] == digest, (
        "MANIFEST.yaml sha256 does not match rules.yaml bytes — recompute it "
        "(sha256sum dif/rules/rules.yaml) and add a CHANGELOG.md entry"
    )
    data = yaml.safe_load(RULES_YAML.read_text())
    assert manifest["version"] == data["version"], "manifest/pack version drift"
    assert manifest.get("channel", "stable") == "stable", "shipped pack must be channel=stable"


def test_changelog_has_an_entry_for_the_current_pack_version():
    version = _manifest()["version"]
    changelog = (PACK_DIR / "CHANGELOG.md").read_text()
    assert f"## {version}" in changelog, (
        f"dif/rules/CHANGELOG.md has no entry for pack {version} — every pack bump is logged"
    )


def test_archived_previous_pack_verifies_against_its_manifest():
    # Rollback (Python leg; the Rust loader has the engine-level test): the archived pack's
    # bytes still match its archived manifest, so pinning MAHSA_RULES at it will boot.
    archive = PACK_DIR / "archive"
    prev_manifest = yaml.safe_load((archive / "MANIFEST-2026.07.1.yaml").read_text())
    prev_pack = archive / "rules-2026.07.1.yaml"
    digest = hashlib.sha256(prev_pack.read_bytes()).hexdigest()
    assert prev_manifest["rules_sha256"] == digest
    assert yaml.safe_load(prev_pack.read_text())["version"] == prev_manifest["version"]
