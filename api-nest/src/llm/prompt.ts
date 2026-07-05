/**
 * Prompt assembly for the Maisha drafting layer. Pure and fully testable: no model, no IO.
 * Faithful port of api/app/llm/prompt.py. The model is a router and narrator, not a calculator:
 * every number it states must be copied verbatim from FACTS; citations only from RULES; if FACTS
 * lacks what the query needs, it abstains.
 */

export const SYSTEM_PROMPT =
  'You are Maisha, the drafting layer of a zero-error Indian startup finance suite. ' +
  'You DO NOT do arithmetic and you never invent numbers. Every number you state MUST be ' +
  'copied verbatim (as a decimal string; money is integer paise) from the FACTS block, ' +
  'which was computed by deterministic, audited engines. Cite statutory rules only from the ' +
  'RULES block, using their exact statute and section. If the FACTS block does not contain ' +
  'what the question needs, set "abstained": true and return an empty "claims" object. ' +
  'Respond ONLY with a JSON object matching the provided schema.';

export interface RuleHint {
  rule_id: string;
  statute: string;
  section: string;
  when: string;
}

// Mirrors dif/rules/rules.yaml (the authoritative set); Mahsa enforces correctness.
export const DOMAIN_RULES: Record<string, RuleHint[]> = {
  gst: [
    { rule_id: 'GST-001', statute: 'CGST Act 2017', section: 'Sec 47 / Rule 61', when: 'gstr3b_days_late > 0' },
    { rule_id: 'GST-002', statute: 'CGST Rules 2017', section: 'Rule 36(4)', when: 'itc_claimed_ratio > 1.05' },
  ],
  payables: [
    { rule_id: 'PAYABLES-001', statute: 'MSMED Act 2006', section: 'Sec 15-16', when: 'msme_max_days_unpaid > 45' },
  ],
  expense: [
    { rule_id: 'EXPENSE-001', statute: 'Internal expense policy', section: 'EXP-1', when: 'over_policy_claims > 0' },
  ],
  compliance: [
    { rule_id: 'COMPLIANCE-002', statute: 'Various (see compliance calendar)', section: '—', when: 'overdue_filings > 0' },
  ],
  tax: [
    { rule_id: 'TAX-001', statute: 'Income Tax Act 1961', section: 'Sec 211 / 234C', when: 'advance_tax_q1_ratio < 0.15' },
  ],
};

export function rulesForDomain(domain: string): RuleHint[] {
  return DOMAIN_RULES[domain] ?? [];
}

function factsBlock(facts: Record<string, any>): string {
  const keys = Object.keys(facts).sort();
  if (keys.length === 0) return '(no facts available)';
  return keys.map((k) => `  ${k}: ${facts[k]}`).join('\n');
}

function rulesBlock(rules: RuleHint[]): string {
  if (rules.length === 0) return '(no statutory rules apply to this domain)';
  return rules.map((r) => `  ${r.rule_id}: ${r.statute} / ${r.section}  (applies when ${r.when})`).join('\n');
}

export function buildUserPrompt(args: {
  domain: string;
  query: string;
  facts: Record<string, any>;
  rules: RuleHint[];
  feedback?: string | null;
  profile?: string;
}): string {
  const fb = args.feedback
    ? `CORRECTION (your previous draft was rejected):\n  ${args.feedback}\n\n`
    : '';
  // Org context personalizes the framing. It is NOT a source of numbers — those come only from FACTS.
  const prof = args.profile ? `ORG PROFILE (context only — never a source of numbers):\n${args.profile}\n\n` : '';
  return (
    `DOMAIN: ${args.domain}\n\n` +
    prof +
    fb +
    `QUESTION:\n  ${args.query}\n\n` +
    `FACTS (the only numbers you may state):\n${factsBlock(args.facts)}\n\n` +
    `RULES (the only citations you may use):\n${rulesBlock(args.rules)}\n\n` +
    'Draft the answer. Set the domain field to the DOMAIN above. Put each number you ' +
    'report into "claims" keyed by metric name, copied verbatim from FACTS. Add a short ' +
    '"narrative". Add "rule_assertions" only for rules whose condition the FACTS meet.'
  );
}
