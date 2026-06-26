"""P4-RULES: the CA-signed rule set (dif/rules/rules.yaml) and the per-domain rules.py owners
stay in lock-step — no orphan rule IDs either way, and every rule cites a statute + section."""

from __future__ import annotations

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
        f"rule-set drift — in Python only: {py_ids - yaml_ids}; "
        f"in YAML only: {yaml_ids - py_ids}"
    )


def test_every_rule_cites_statute_and_section():
    for rule in _yaml_rules():
        for field in ("id", "domain", "statute", "section", "severity"):
            assert rule.get(field), f"rule {rule.get('id')} missing '{field}'"
