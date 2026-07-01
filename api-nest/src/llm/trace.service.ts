/**
 * Persistence for the LLM trace. Faithful port of api/app/core/trace_store.py. Separate from the
 * audit log: the audit log is the tamper-evident financial record; the trace is repro metadata
 * for the drafting layer. We persist hashes, never raw prompts.
 */
import { createHash } from 'crypto';
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { LlmTrace } from '../common/shared.entities';
import { ActionClaim, canonicalClaim } from './schema';

function sortKeys(v: any): any {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    const out: Record<string, any> = {};
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k]);
    return out;
  }
  return v;
}

/** A reproducibility key over the deterministic inputs (domain + query + snapshot). */
export function inputHash(domain: string, query: string | null, snapshot: Record<string, any>): string {
  const blob = JSON.stringify(sortKeys({ domain, query, snapshot }));
  return createHash('sha256').update(blob).digest('hex');
}

@Injectable()
export class TraceService {
  constructor(@InjectRepository(LlmTrace) private readonly repo: Repository<LlmTrace>) {}

  async append(args: {
    timestamp: string;
    domain: string;
    auditHash: string | null;
    modelLabel: string;
    inputSha256: string;
    claim: ActionClaim | null;
    attempts: number;
    verified: boolean;
    requiresApproval: boolean;
    latencyMs: number;
  }): Promise<void> {
    await this.repo.save(
      this.repo.create({
        timestamp: args.timestamp,
        domain: args.domain,
        audit_hash: args.auditHash,
        model_label: args.modelLabel,
        input_sha256: args.inputSha256,
        claim_sha256: args.claim ? createHash('sha256').update(canonicalClaim(args.claim)).digest('hex') : null,
        attempts: args.attempts,
        verified: args.verified ? 1 : 0,
        requires_approval: args.requiresApproval ? 1 : 0,
        latency_ms: args.latencyMs,
      }),
    );
  }
}
