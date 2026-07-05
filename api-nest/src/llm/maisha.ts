/**
 * Maisha — the drafting orchestrator. Faithful port of api/app/llm/maisha.py. Turns
 * (snapshot, query, domain) into a strict ActionClaim by: enriching the snapshot into
 * deterministic FACTS (tools, never LLM math), building the prompt, asking the LLM for a
 * schema-constrained claim, and parsing it. It is a *drafter* — Mahsa recomputes/validates.
 */
import { Logger } from '@nestjs/common';

import { LLMClient } from './client';
import { scanInput } from './guardrails';
import { buildUserPrompt, rulesForDomain, SYSTEM_PROMPT } from './prompt';
import { ACTION_CLAIM_SCHEMA, ActionClaim, parseClaim } from './schema';
import { enrich } from './tools';

/** Anything that drafts an ActionClaim from a snapshot + query. */
export interface ClaimProducer {
  readonly label: string;
  produce(args: {
    snapshot: Record<string, any>;
    query: string;
    domain: string;
    feedback?: string | null;
    profile?: string;
  }): Promise<ActionClaim>;
}

export class MaishaGenerator implements ClaimProducer {
  private readonly log = new Logger('maisha.guardrails');

  constructor(
    private readonly client: LLMClient,
    readonly label = 'llm',
    private readonly redactPii = false,
  ) {}

  async produce(args: {
    snapshot: Record<string, any>;
    query: string;
    domain: string;
    feedback?: string | null;
    profile?: string;
  }): Promise<ActionClaim> {
    // Input guardrails run before the model sees anything.
    const guard = scanInput(args.query, { redactPii: this.redactPii });
    if (!guard.allowed) {
      this.log.warn(`query for domain '${args.domain}' blocked: ${guard.findings.join(',')}`);
      return {
        domain: args.domain,
        narrative: 'Query blocked by input guardrails (possible prompt injection).',
        claims: {},
        rule_assertions: [],
        abstained: true,
        confidence: null,
      };
    }
    if (guard.findings.length) {
      this.log.log(`redacted PII before send for domain '${args.domain}': ${guard.findings.join(',')}`);
    }

    const facts = enrich(args.snapshot);
    const user = buildUserPrompt({
      domain: args.domain,
      query: guard.text,
      facts,
      rules: rulesForDomain(args.domain),
      feedback: args.feedback,
      profile: args.profile,
    });
    const raw = await this.client.complete({ system: SYSTEM_PROMPT, user, schema: ACTION_CLAIM_SCHEMA });
    const claim = parseClaim(raw);
    // The router already decided the domain; the model doesn't get to reclassify it.
    if (claim.domain !== args.domain) claim.domain = args.domain;
    return claim;
  }
}
