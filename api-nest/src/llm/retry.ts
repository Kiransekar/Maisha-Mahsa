/**
 * The evaluator-optimizer loop. Faithful port of api/app/llm/retry.py. The *evaluator* is the
 * deterministic fact set: every number a claim states must be a value the audited engines
 * actually produced (the Golden Rule applied to the draft, live). The *optimizer* is bounded
 * regeneration: on an unbacked number we feed the discrepancy back and ask again. On exhaustion
 * we fall back to a claim built directly from the facts and flag it for approval — never ship an
 * unverified number. Mahsa's verdict describes the books, not the draft, so it is not a retry
 * trigger; its triggered rules are passed into the feedback.
 */
import { FoldResult } from '../mahsa/mahsa.service';
import { ClaimProducer } from './maisha';
import { ActionClaim, RuleAssertion } from './schema';
import { enrich } from './tools';

export interface DraftResult {
  claim: ActionClaim;
  attempts: number;
  verified: boolean; // every stated number is backed by a deterministic fact (or a clean abstain)
  requiresApproval: boolean; // Mahsa flagged the books, or the draft fell back after exhaustion
}

const canon = (v: any): string => String(v);

export function allowedValues(facts: Record<string, any>): Set<string> {
  return new Set(Object.values(facts).map(canon));
}

/** Claim entries whose value is not any deterministic fact value — i.e. invented numbers. */
export function unbackedNumbers(claim: ActionClaim, allowed: Set<string>): [string, string][] {
  return Object.entries(claim.claims).filter(([, v]) => !allowed.has(v));
}

function triggeredAssertions(fold: FoldResult): RuleAssertion[] {
  return fold.validation.triggered.map((t) => ({ rule_id: t.id, statute: t.statute, section: t.section }));
}

/** A fully-backed claim assembled directly from the facts + Mahsa's triggered rules. */
export function fallbackClaim(domain: string, facts: Record<string, any>, fold: FoldResult): ActionClaim {
  const claims: Record<string, string> = {};
  for (const [k, v] of Object.entries(facts)) {
    if (typeof v === 'number') claims[k] = canon(v);
  }
  return {
    domain,
    narrative:
      'Auto-generated from verified figures; the drafted answer failed number verification and is pending review.',
    claims,
    rule_assertions: triggeredAssertions(fold),
    abstained: false,
    confidence: null,
  };
}

function feedbackFor(bad: [string, string][], fold: FoldResult): string {
  const badStr = bad.map(([k, v]) => `${k}=${v}`).join('; ');
  const triggered = fold.validation.triggered.map((t) => t.id).join(', ') || 'none';
  return (
    `These reported numbers are not in the FACTS block and must not be used: ${badStr}. ` +
    `State only values present in FACTS. Mahsa triggered these rules: ${triggered}.`
  );
}

export async function generateVerified(
  generator: ClaimProducer,
  args: { snapshot: Record<string, any>; query: string; domain: string; fold: FoldResult; maxRetries: number; profile?: string },
): Promise<DraftResult> {
  const facts = enrich(args.snapshot);
  const allowed = allowedValues(facts);
  let feedback: string | null = null;

  for (let attempt = 1; attempt <= args.maxRetries + 1; attempt++) {
    const claim = await generator.produce({ snapshot: args.snapshot, query: args.query, domain: args.domain, feedback, profile: args.profile });
    const bad = unbackedNumbers(claim, allowed);
    if (bad.length === 0) {
      return { claim, attempts: attempt, verified: true, requiresApproval: args.fold.shape.requires_approval };
    }
    feedback = feedbackFor(bad, args.fold);
  }

  return {
    claim: fallbackClaim(args.domain, facts, args.fold),
    attempts: args.maxRetries + 1,
    verified: false,
    requiresApproval: true,
  };
}
