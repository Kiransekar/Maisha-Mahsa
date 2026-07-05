/**
 * The Maisha-Mahsa loop (PRD §10): build a domain snapshot → fold/validate via Mahsa → optional
 * verified LLM draft → seal into the hash-chained audit log → return for rendering. The single
 * choke point that guarantees the Golden Rule: every result a user sees was validated by Mahsa
 * and recorded. Mirrors api/app/core/loop.py.
 */
import { Inject, Injectable, Optional } from '@nestjs/common';

import { AuditService } from '../audit/audit.service';
import { MemoryService } from '../memory/memory.service';
import { ClaimProducer } from '../llm/maisha';
import { generateVerified } from '../llm/retry';
import { ActionClaim } from '../llm/schema';
import { inputHash, TraceService } from '../llm/trace.service';
import { FoldResult, MahsaService } from '../mahsa/mahsa.service';

export const CLAIM_PRODUCER = 'CLAIM_PRODUCER';

/** A domain service the loop can fold: it produces a deterministic snapshot for Mahsa. */
export interface SnapshotProducer {
  readonly domain: string;
  buildSnapshot(asOf?: string): Promise<Record<string, any>> | Record<string, any>;
}

export interface LoopOutcome {
  snapshot: Record<string, any>;
  fold: FoldResult;
  auditHash: string;
  requiresApproval: boolean;
  claim: ActionClaim | null;
  claimVerified: boolean | null; // null when no LLM ran
}

@Injectable()
export class LoopService {
  constructor(
    private readonly mahsa: MahsaService,
    private readonly audit: AuditService,
    @Optional() private readonly trace?: TraceService,
    @Optional() @Inject(CLAIM_PRODUCER) private readonly generator?: ClaimProducer | null,
    @Optional() private readonly memory?: MemoryService,
  ) {}

  async run(args: {
    service: SnapshotProducer;
    timestamp: string;
    asOf?: string;
    query?: string;
    action?: string;
    userId?: string;
    maxRetries?: number;
  }): Promise<LoopOutcome> {
    const { service, timestamp } = args;
    const snapshot = await service.buildSnapshot(args.asOf);

    // Mahsa's verdict is the source of truth, independent of any LLM draft (the Golden Rule).
    const fold = await this.mahsa.fold(snapshot, { domain: service.domain, query: args.query });

    // Optional drafting step: the LLM proposes a claim, every number is checked against the
    // deterministic facts, unbacked numbers trigger bounded regeneration; on exhaustion a
    // fact-built fallback is flagged for approval. The claim never overrides Mahsa.
    let claim: ActionClaim | null = null;
    let claimVerified: boolean | null = null;
    let attempts = 0;
    let latencyMs = 0;
    let requiresApproval = fold.shape.requires_approval;
    if (this.generator && args.query) {
      const started = Date.now();
      // CFO Profile personalizes the draft's framing — context only, never a source of numbers.
      const profile = this.memory ? await this.memory.profileText().catch(() => '') : '';
      const draft = await generateVerified(this.generator, {
        snapshot,
        query: args.query,
        domain: service.domain,
        fold,
        profile,
        maxRetries: args.maxRetries ?? 2,
      });
      latencyMs = Date.now() - started;
      claim = draft.claim;
      claimVerified = draft.verified;
      attempts = draft.attempts;
      requiresApproval = requiresApproval || draft.requiresApproval;
    }

    const entry = await this.audit.append({
      timestamp,
      action: args.action ?? 'fold',
      domain: service.domain,
      user_id: args.userId ?? process.env.MAISHA_DEFAULT_USER_ID ?? 'founder',
      query: args.query ?? null,
      intent_global: fold.global_intent,
      intent_domain: fold.domain_intent ?? null,
      validation_status: fold.validation.status,
      rules_version: fold.rules_version,
    });

    // LLM trace (observability; hashes only) — only when a draft was produced.
    if (claim !== null && this.trace) {
      await this.trace.append({
        timestamp,
        domain: service.domain,
        auditHash: entry.this_hash,
        modelLabel: this.generator?.label ?? 'unknown',
        inputSha256: inputHash(service.domain, args.query ?? null, snapshot),
        claim,
        attempts,
        verified: !!claimVerified,
        requiresApproval,
        latencyMs,
      });
    }

    return {
      snapshot,
      fold,
      auditHash: entry.this_hash,
      requiresApproval,
      claim,
      claimVerified,
    };
  }
}
