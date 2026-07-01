/**
 * Input guardrails for the drafting layer. Faithful port of api/app/llm/guardrails.py.
 * Two checks run on the user query BEFORE the model sees it:
 *  - prompt-injection / jailbreak detection → refuse to draft and abstain (safe default).
 *  - PII redaction (only when the model is a cloud provider) → mask Indian PII before it leaves.
 * Pure and deterministic: same input → same findings, no IO.
 */

const INJECTION_PATTERNS: RegExp[] = [
  /ignore\s+(all\s+|the\s+|your\s+)?(previous|prior|above)\s+(instructions|prompts?)/i,
  /disregard\s+(all\s+|the\s+|your\s+)?(previous|prior|above)?\s*(instructions|rules)/i,
  /\byou\s+are\s+now\b/i,
  /\bact\s+as\b/i,
  /\bsystem\s+prompt\b/i,
  /reveal\s+(the\s+|your\s+)?(system\s+prompt|instructions|secret|password|api[\s_-]?key)/i,
  /\bjailbreak\b/i,
  /\bnew\s+instructions\s*:/i,
  /override\s+(the\s+|your\s+)?(rules|instructions|guardrails)/i,
];

// Order matters: GSTIN before PAN (GSTIN embeds a PAN). [name, pattern]
const PII_PATTERNS: [string, RegExp][] = [
  ['gstin', /\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b/g],
  ['pan', /\b[A-Z]{5}\d{4}[A-Z]\b/g],
  ['aadhaar', /\b\d{4}\s?\d{4}\s?\d{4}\b/g],
  ['email', /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g],
  ['phone', /(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)/g],
];

export interface GuardResult {
  allowed: boolean; // false when a prompt-injection attempt is detected
  text: string; // the (possibly PII-redacted) query to actually send to the model
  injection: boolean;
  findings: string[]; // e.g. ["injection", "pii:pan"]
}

export function scanInput(query: string, opts: { redactPii?: boolean } = {}): GuardResult {
  const findings: string[] = [];
  const injection = INJECTION_PATTERNS.some((p) => p.test(query));
  if (injection) findings.push('injection');

  let text = query;
  if (opts.redactPii) {
    for (const [name, pat] of PII_PATTERNS) {
      // Replace with a callback so we never touch the /g regex's stateful lastIndex via .test().
      let hit = false;
      const next = text.replace(pat, () => {
        hit = true;
        return `[REDACTED-${name.toUpperCase()}]`;
      });
      if (hit) {
        findings.push(`pii:${name}`);
        text = next;
      }
    }
  }

  return { allowed: !injection, text, injection, findings };
}
