"""Statutory-oracle framework + runner (MMX-1.0 §WS1.E1, QG.1) — CI-blocking.

Loads every CA-vector under ``vectors/*.yaml`` and asserts the registered target reproduces
``expected`` exactly. Each vector carries its schema (§0.6):
    {id, statute, section, source|citation_url, ca_initials, ca_date, target, inputs, expected}
For dict results, ``expected`` is a subset match (assert only the keys given) so a vector can
pin one figure without over-specifying. Runs under `make test-py`; a failing vector blocks the
merge. A statutory value never enters via a test — it enters as vector data with a cited source,
and TARGETS only names which pure engine callable computes it.

The Rust-parity leg (run each vector against Mahsa too, diff to the paisa) is WS3; not wired
yet — add a RUST_TARGETS map and a second assertion when the path is ported.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core import statutory_regime
from app.core.statutory_wage import statutory_wage_base
from app.domains.payables import payables_calc
from app.domains.payroll import service as payroll_service
from app.domains.payroll import statutory as payroll
from app.domains.tax import tax_calc
from app.domains.vault import vault_calc


def _tds(**kw: Any) -> dict[str, Any]:
    r = payables_calc.tds_on_payment(**kw)
    return {"applicable": r["applicable"], "tds_paise": int(r["tds_paise"])}


def _esi(**kw: Any) -> list[int]:
    emp, empr = payroll.esi(**kw)
    return [int(emp), int(empr)]


def _itr(**kw: Any) -> dict[str, Any]:
    r = tax_calc.itr_computation(**kw)
    return {k: r[k] for k in ("form", "normal_tax", "mat", "tax_payable")}


def _retention(**kw: Any) -> str | None:
    return vault_calc.retention_until(**kw)


def _regime(credit_date: str | None = None, payment_date: str | None = None) -> str:
    cd = date.fromisoformat(credit_date) if credit_date else None
    pd = date.fromisoformat(payment_date) if payment_date else None
    return statutory_regime.regime_for(cd, pd)


def _form_name(**kw: Any) -> str:
    return statutory_regime.form_name(**kw)


def _wage_base(**kw: Any) -> int:
    return int(statutory_wage_base(**kw))


def _payroll_components(**kw: Any) -> dict[str, int]:
    # Proves the §WS1.B1 wiring: PF/ESI in compute_components run on the s.2(y) wage base.
    return payroll_service.compute_components(**kw)


def _late_fee_234e(**kw: Any) -> int:
    return int(tax_calc.late_fee_234e(**kw))


def _gratuity_hybrid(**kw: Any) -> int:
    kw = dict(kw)
    for key in ("doj", "exit_date", "boundary"):
        kw[key] = date.fromisoformat(kw[key])
    return int(payroll.gratuity_hybrid(**kw))


# target name -> pure engine callable returning JSON-comparable output. Add a line to port a path.
TARGETS: dict[str, Callable[..., Any]] = {
    "tds_on_payment": _tds,
    "esi": _esi,
    "itr_computation": _itr,
    "retention_until": _retention,
    "regime_for": _regime,
    "form_name": _form_name,
    "statutory_wage_base": _wage_base,
    "payroll_components": _payroll_components,
    "gratuity_hybrid": _gratuity_hybrid,
    "late_fee_234e": _late_fee_234e,
}

VECTOR_DIR = Path(__file__).parent / "vectors"
REQUIRED_FIELDS = {"id", "statute", "section", "target", "inputs", "expected"}


def _load() -> list[dict[str, Any]]:
    vectors: list[dict[str, Any]] = []
    for f in sorted(VECTOR_DIR.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text()) or []
        items = doc["vectors"] if isinstance(doc, dict) else doc
        for v in items:
            v["_file"] = f.name
            vectors.append(v)
    return vectors


VECTORS = _load()


def test_vectors_exist() -> None:
    # Guard against a silently-empty oracle (a suite that cannot fail is a defect, §0.5).
    assert VECTORS, "no oracle vectors loaded — the statutory oracle must never be empty"


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: f"{v['_file']}::{v['id']}")
def test_oracle_vector(v: dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - v.keys()
    assert not missing, f"vector {v['id']} missing fields: {missing}"
    assert "source" in v or "citation_url" in v, f"vector {v['id']} has no cited source (§0.6)"

    target = TARGETS.get(v["target"])
    assert target is not None, f"vector {v['id']}: unknown target {v['target']!r}"

    result = target(**v["inputs"])
    expected = v["expected"]
    if isinstance(expected, dict) and isinstance(result, dict):
        for k, want in expected.items():
            assert result.get(k) == want, f"{v['id']} [{k}]: expected {want}, got {result.get(k)}"
    else:
        assert result == expected, f"{v['id']}: expected {expected}, got {result}"
