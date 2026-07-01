/**
 * Deterministic tools the drafting layer relies on instead of doing its own arithmetic.
 * Faithful port of api/app/llm/tools.py. Each tool is a thin wrapper over audited domain calc
 * functions and produces canonical decimal STRINGS (paise for money) so its outputs drop
 * straight into an ActionClaim. `enrich` flattens a Mahsa snapshot into a flat facts map and
 * applies every tool whose inputs are present — so every number the model sees (incl. derived
 * ones like runway) was computed deterministically, never by the LLM.
 */
import { lateFee3b } from '../domains/gst/gst.calc';

export class ToolError extends Error {}

function asInt(facts: Record<string, any>, key: string): number {
  const v = facts[key];
  const n = typeof v === 'number' ? v : Number(v);
  if (v === undefined || v === null || !Number.isFinite(n) || !Number.isInteger(n)) {
    throw new ToolError(`tool input '${key}' is missing or non-integer: ${JSON.stringify(v)}`);
  }
  return n;
}

interface Tool {
  name: string;
  description: string;
  inputs: string[];
  fn: (facts: Record<string, any>) => Record<string, string>;
}

function treasuryRunway(facts: Record<string, any>): Record<string, string> {
  const cash = asInt(facts, 'cash');
  const netBurn = Math.max(0, asInt(facts, 'monthly_burn') - asInt(facts, 'monthly_revenue'));
  if (netBurn === 0) return { net_burn_paise: '0' }; // cash-flow positive
  return { net_burn_paise: String(netBurn), runway_months: String(Math.round((cash / netBurn) * 100) / 100) };
}

function gstLateFee(facts: Record<string, any>): Record<string, string> {
  return { gstr3b_late_fee_paise: String(lateFee3b(asInt(facts, 'gstr3b_days_late'))) };
}

const REGISTRY: Tool[] = [
  {
    name: 'treasury_runway',
    description: 'Months of runway = cash / (monthly burn − monthly revenue).',
    inputs: ['cash', 'monthly_burn', 'monthly_revenue'],
    fn: treasuryRunway,
  },
  {
    name: 'gst_late_fee_3b',
    description: 'GSTR-3B late fee (₹50/day, capped) from days late.',
    inputs: ['gstr3b_days_late'],
    fn: gstLateFee,
  },
];

/** Flatten a Mahsa snapshot (top-level scalars + the `metrics` sub-dict) into one map. */
export function flatten(snapshot: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(snapshot)) {
    if (k === 'metrics') continue;
    if (typeof v === 'number' || typeof v === 'string') out[k] = v;
  }
  const metrics = snapshot.metrics;
  if (metrics && typeof metrics === 'object') {
    for (const [k, v] of Object.entries(metrics)) {
      if (typeof v === 'number' || typeof v === 'string') out[k] = v;
    }
  }
  return out;
}

/** Flatten then apply every applicable tool, merging deterministic derived values in. */
export function enrich(snapshot: Record<string, any>): Record<string, any> {
  const facts = flatten(snapshot);
  for (const tool of REGISTRY) {
    if (tool.inputs.every((k) => k in facts)) Object.assign(facts, tool.fn(facts));
  }
  return facts;
}
