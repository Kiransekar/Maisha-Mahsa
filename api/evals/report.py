"""Render eval results as human-readable text or machine-readable JSON."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a runtime import cycle with harness.py
    from .harness import CaseResult


def _summary(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    inconsistent = [r.id for r in results if not r.consistent]
    return {
        "cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(100.0 * passed / total, 1) if total else 0.0,
        "inconsistent": inconsistent,
    }


def render_json(results: list[CaseResult]) -> str:
    payload = {
        "summary": _summary(results),
        "results": [
            {
                "id": r.id,
                "domain": r.domain,
                "k": r.k,
                "consistent": r.consistent,
                "passed": r.passed,
                "scores": [
                    {"name": s.name, "passed": s.passed, "detail": s.detail} for s in r.scores
                ],
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)


def render_text(results: list[CaseResult]) -> str:
    lines: list[str] = []
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        passk = "ok" if r.consistent else "DRIFT"
        lines.append(f"[{mark}] {r.id}  ({r.domain}, pass^{r.k}={passk})")
        for s in r.scores:
            smark = "ok  " if s.passed else "FAIL"
            lines.append(f"        {smark} {s.name}: {s.detail}")
    summary = _summary(results)
    lines.append("")
    lines.append(
        f"{summary['passed']}/{summary['cases']} cases passed ({summary['pass_rate']}%)."
    )
    if summary["inconsistent"]:
        lines.append(f"pass^k drift in: {', '.join(summary['inconsistent'])}")
    return "\n".join(lines)
