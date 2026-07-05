/**
 * Hash-chained, append-only audit log (PRD §11.2). Faithful port of api/app/core/audit.py.
 * this_hash = sha256(prev_hash || canonicalJson(entry)). Canonical JSON = sorted keys,
 * no whitespace — MUST match Python's json.dumps(sort_keys, separators=(",",":")).
 */
import { createHash } from 'crypto';

export const GENESIS_HASH = '0'.repeat(64);

export interface AuditCore {
  timestamp: string;
  action: string;
  domain: string;
  user_id: string;
  query: string | null;
  intent_global: number[] | null;
  intent_domain: number[] | null;
  validation_status: string;
  rules_version: string;
}

export interface AuditEntry extends AuditCore {
  prev_hash: string;
  this_hash: string;
}

/** Deterministic JSON for this chain: recursively sorted keys, no insignificant whitespace.
 * Internally consistent (verifyChain) — not asserted to be byte-identical to Python's json.dumps. */
export function canonicalJson(payload: unknown): string {
  return JSON.stringify(sortKeys(payload));
}

function sortKeys(v: any): any {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    const out: Record<string, any> = {};
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k]);
    return out;
  }
  // Reject non-finite numbers: NaN/Infinity serialize to `null`, letting distinct entries collide.
  if (typeof v === 'number' && !Number.isFinite(v)) {
    throw new Error('audit entry contains a non-finite number; refusing to seal an ambiguous hash');
  }
  return v;
}

export function computeHash(prevHash: string, core: AuditCore): string {
  return createHash('sha256')
    .update(prevHash, 'utf-8')
    .update(canonicalJson(core), 'utf-8')
    .digest('hex');
}

export function corePayload(e: AuditCore): AuditCore {
  // Explicit shape so key set matches Python exactly (order is normalized by canonicalJson).
  return {
    timestamp: e.timestamp,
    action: e.action,
    domain: e.domain,
    user_id: e.user_id,
    query: e.query,
    intent_global: e.intent_global,
    intent_domain: e.intent_domain,
    validation_status: e.validation_status,
    rules_version: e.rules_version,
  };
}

export function makeEntry(prevHash: string, core: AuditCore): AuditEntry {
  return { ...corePayload(core), prev_hash: prevHash, this_hash: computeHash(prevHash, core) };
}

export function verifyChain(entries: AuditEntry[]): boolean {
  let prev = GENESIS_HASH;
  for (const e of entries) {
    if (e.prev_hash !== prev) return false;
    if (computeHash(prev, corePayload(e)) !== e.this_hash) return false;
    prev = e.this_hash;
  }
  return true;
}
