"""Prompt assembly for the Maisha drafting layer. Pure and fully testable: no model, no IO.

The contract pushed onto the model is deliberately narrow — it is a *router and narrator*,
not a calculator:

* every number it states must be copied verbatim from the FACTS block (which the
  deterministic tools/engines produced);
* citations may only come from the RULES block;
* if FACTS lacks what the query needs, it abstains.

This keeps the model inside the lane Mahsa will re-check, and is what the pass^k eval gate
holds it to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SYSTEM_PROMPT = (
    "You are Maisha, the drafting layer of a zero-error Indian startup finance suite. "
    "You DO NOT do arithmetic and you never invent numbers. Every number you state MUST be "
    "copied verbatim (as a decimal string; money is integer paise) from the FACTS block, "
    "which was computed by deterministic, audited engines. Cite statutory rules only from the "
    "RULES block, using their exact statute and section. If the FACTS block does not contain "
    "what the question needs, set \"abstained\": true and return an empty \"claims\" object. "
    "Respond ONLY with a JSON object matching the provided schema."
)


@dataclass(frozen=True)
class RuleHint:
    rule_id: str
    statute: str
    section: str
    when: str


# Citation hints for the domains whose rules the model may assert. Mirrors dif/rules/rules.yaml
# (the authoritative set); the eval's citation scorer and Mahsa enforce correctness.
DOMAIN_RULES: dict[str, list[RuleHint]] = {
    "gst": [
        RuleHint("GST-001", "CGST Act 2017", "Sec 47 / Rule 61", "gstr3b_days_late > 0"),
        RuleHint("GST-002", "CGST Rules 2017", "Rule 36(4)", "itc_claimed_ratio > 1.05"),
    ],
    "payables": [
        RuleHint("PAYABLES-001", "MSMED Act 2006", "Sec 15-16", "msme_max_days_unpaid > 45"),
    ],
    "expense": [
        RuleHint("EXPENSE-001", "Internal expense policy", "EXP-1", "over_policy_claims > 0"),
    ],
    "compliance": [
        RuleHint(
            "COMPLIANCE-002", "Various (see compliance calendar)", "—", "overdue_filings > 0"
        ),
    ],
    "tax": [
        RuleHint("TAX-001", "Income Tax Act 1961", "Sec 211 / 234C", "advance_tax_q1_ratio < 0.15"),
    ],
}


def rules_for_domain(domain: str) -> list[RuleHint]:
    return DOMAIN_RULES.get(domain, [])


def _facts_block(facts: dict[str, Any]) -> str:
    if not facts:
        return "(no facts available)"
    return "\n".join(f"  {k}: {v}" for k, v in sorted(facts.items()))


def _rules_block(rules: list[RuleHint]) -> str:
    if not rules:
        return "(no statutory rules apply to this domain)"
    return "\n".join(
        f"  {r.rule_id}: {r.statute} / {r.section}  (applies when {r.when})" for r in rules
    )


def build_user_prompt(
    *,
    domain: str,
    query: str,
    facts: dict[str, Any],
    rules: list[RuleHint],
    feedback: str | None = None,
) -> str:
    fb = f"CORRECTION (your previous draft was rejected):\n  {feedback}\n\n" if feedback else ""
    return (
        f"DOMAIN: {domain}\n\n"
        f"{fb}"
        f"QUESTION:\n  {query}\n\n"
        f"FACTS (the only numbers you may state):\n{_facts_block(facts)}\n\n"
        f"RULES (the only citations you may use):\n{_rules_block(rules)}\n\n"
        "Draft the answer. Set the domain field to the DOMAIN above. Put each number you "
        "report into \"claims\" keyed by metric name, copied verbatim from FACTS. Add a short "
        "\"narrative\". Add \"rule_assertions\" only for rules whose condition the FACTS meet."
    )
