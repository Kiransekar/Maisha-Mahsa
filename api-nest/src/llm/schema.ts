/**
 * The ActionClaim — the strict, typed structure the Maisha LLM layer must emit. Faithful port
 * of api/app/llm/schema.py. It is *drafted* by the model and never trusted as a verdict: every
 * number is recomputed by Mahsa downstream (Golden Rule). Money is integer paise as decimal
 * STRINGS, never floats — so equality is exact (the pass^k / verification checks are string
 * comparisons) and no float rounding error can enter through a claim.
 */

export interface RuleAssertion {
  rule_id: string;
  statute: string;
  section: string;
}

export function citation(a: RuleAssertion): string {
  return `${a.statute} / ${a.section}`;
}

export interface ActionClaim {
  domain: string;
  narrative: string;
  claims: Record<string, string>; // metric -> canonical decimal string (paise for money)
  rule_assertions: RuleAssertion[];
  abstained: boolean;
  confidence: number | null;
}

/** JSON Schema for constrained decoding (Ollama `format`, Claude tool `input_schema`). */
export const ACTION_CLAIM_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    domain: { type: 'string' },
    narrative: { type: 'string' },
    claims: { type: 'object', additionalProperties: { type: 'string' } },
    rule_assertions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          rule_id: { type: 'string' },
          statute: { type: 'string' },
          section: { type: 'string' },
        },
        required: ['rule_id', 'statute', 'section'],
      },
    },
    abstained: { type: 'boolean' },
    confidence: { type: ['number', 'null'] },
  },
  required: ['domain'],
} as const;

/** Build a claim from raw model output, applying defaults and rejecting the wrong shapes
 * (mirrors Pydantic `extra="forbid"` + `StrictStr`: claim values MUST be strings). */
export function parseClaim(raw: any): ActionClaim {
  if (raw === null || typeof raw !== 'object') {
    throw new Error(`claim is not an object: ${typeof raw}`);
  }
  const allowed = new Set([
    'domain',
    'narrative',
    'claims',
    'rule_assertions',
    'abstained',
    'confidence',
  ]);
  for (const k of Object.keys(raw)) {
    if (!allowed.has(k)) throw new Error(`claim has forbidden field: ${k}`);
  }
  if (typeof raw.domain !== 'string') throw new Error('claim.domain must be a string');

  const claims: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw.claims ?? {})) {
    if (typeof v !== 'string') throw new Error(`claim value for ${k} must be a string (got ${typeof v})`);
    claims[k] = v;
  }

  const rule_assertions: RuleAssertion[] = (raw.rule_assertions ?? []).map((a: any) => {
    if (!a || typeof a.rule_id !== 'string' || typeof a.statute !== 'string' || typeof a.section !== 'string') {
      throw new Error('rule_assertion needs string rule_id, statute, section');
    }
    return { rule_id: a.rule_id, statute: a.statute, section: a.section };
  });

  return {
    domain: raw.domain,
    narrative: typeof raw.narrative === 'string' ? raw.narrative : '',
    claims,
    rule_assertions,
    abstained: raw.abstained === true,
    confidence: typeof raw.confidence === 'number' ? raw.confidence : null,
  };
}

/** Stable serialization for equality (sorted keys) — mirrors ActionClaim.canonical(). */
export function canonicalClaim(claim: ActionClaim): string {
  return JSON.stringify(sortKeys(claim));
}

function sortKeys(v: any): any {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    const out: Record<string, any> = {};
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k]);
    return out;
  }
  return v;
}
