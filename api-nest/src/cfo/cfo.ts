/**
 * The CFO layer: collect every domain's health through Mahsa into one scorecard, and compose the
 * daily brief (PRD §6.1). Faithful port of api/app/core/cfo.py. `collectHealth` folds all domains;
 * `composeBrief` / `briefPayload` are pure.
 */
import { MahsaService } from '../mahsa/mahsa.service';
import { SnapshotProducer } from '../core/loop.service';

export interface DomainHealth {
  domain: string;
  score: number | null; // 0..100 (domain sub-vector score, else global)
  status: string; // green / yellow / red
  requires_approval: boolean;
  banners: Record<string, any>[];
}

const colorOf = (status: string): string =>
  ({ green: 'green', yellow: 'amber', red: 'red' })[status] ?? 'green';

/** Fold every registered domain and collect its health. Throws (MahsaError) if the sidecar is
 * unreachable — the caller decides whether to degrade. */
export async function collectHealth(
  services: SnapshotProducer[],
  mahsa: MahsaService,
  asOf?: string,
): Promise<DomainHealth[]> {
  const out: DomainHealth[] = [];
  for (const service of services) {
    const snapshot = await service.buildSnapshot(asOf);
    const fold = await mahsa.fold(snapshot, { domain: service.domain });
    let score = fold.shape.domain_score;
    if (score === null || score === undefined) score = fold.shape.global_score;
    out.push({
      domain: service.domain,
      score: score !== null && score !== undefined ? Math.round(score * 10) / 10 : null,
      status: fold.validation.status,
      requires_approval: fold.shape.requires_approval,
      banners: fold.shape.banners,
    });
  }
  return out;
}

export interface DailyBrief {
  as_of: string;
  scorecard: DomainHealth[];
  needs_attention: DomainHealth[];
  approvals_pending: DomainHealth[];
  overall_score: number | null;
}

/** Compose the 8pm CFO brief from collected health. Pure. */
export function composeBrief(asOf: string, health: DomainHealth[]): DailyBrief {
  const scored = health.filter((h) => h.score !== null).map((h) => h.score as number);
  const overall = scored.length ? Math.round((scored.reduce((a, b) => a + b, 0) / scored.length) * 10) / 10 : null;
  const order: Record<string, number> = { red: 0, yellow: 1, green: 2 };
  const scorecard = [...health].sort(
    (a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3) || a.domain.localeCompare(b.domain),
  );
  return {
    as_of: asOf,
    scorecard,
    needs_attention: scorecard.filter((h) => h.status === 'red' || h.status === 'yellow'),
    approvals_pending: scorecard.filter((h) => h.requires_approval),
    overall_score: overall,
  };
}

export interface BriefRow {
  domain: string;
  score: number | null;
  status: string;
  color: string;
  requires_approval: boolean;
  banners: Record<string, any>[];
}
export interface BriefPayload {
  as_of: string;
  overall_score: number | null;
  scorecard: BriefRow[];
  needs_attention: BriefRow[];
  approvals_pending: BriefRow[];
}

/** JSON-able view of a brief (for renderers and API responses). */
export function briefPayload(brief: DailyBrief): BriefPayload {
  const row = (h: DomainHealth): BriefRow => ({
    domain: h.domain,
    score: h.score,
    status: h.status,
    color: colorOf(h.status),
    requires_approval: h.requires_approval,
    banners: h.banners,
  });
  return {
    as_of: brief.as_of,
    overall_score: brief.overall_score,
    scorecard: brief.scorecard.map(row),
    needs_attention: brief.needs_attention.map(row),
    approvals_pending: brief.approvals_pending.map(row),
  };
}
