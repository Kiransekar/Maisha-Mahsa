/**
 * Eval-gated model routing. Faithful port of api/app/llm/routing.py. Pick the provider per
 * DOMAIN from measured eval quality: keep the cheap local model where it is good enough, fall
 * back to the stronger cloud model only where it isn't. For a zero-error finance product the bar
 * is strict — the default threshold is 1.0 (the local model must be perfect on a domain's golden
 * cases to serve it). `decideRoutes` is pure; `RoutedGenerator` dispatches per domain.
 */
import { ClaimProducer } from './maisha';
import { ActionClaim } from './schema';

export interface DomainScore {
  domain: string;
  provider: string;
  passRate: number; // 0..1 fraction of the domain's golden cases passed
}

export function decideRoutes(
  scores: DomainScore[],
  opts: { primary?: string; fallback?: string; threshold?: number } = {},
): Record<string, string> {
  const primary = opts.primary ?? 'ollama';
  const fallback = opts.fallback ?? 'claude';
  const threshold = opts.threshold ?? 1.0;

  const primaryRate: Record<string, number> = {};
  for (const s of scores) {
    if (s.provider === primary) primaryRate[s.domain] = Math.max(primaryRate[s.domain] ?? 0, s.passRate);
  }
  const domains = [...new Set(scores.map((s) => s.domain))].sort();
  const routes: Record<string, string> = {};
  for (const d of domains) routes[d] = (primaryRate[d] ?? 0) >= threshold ? primary : fallback;
  return routes;
}

/** Dispatches each draft to the provider chosen for its domain, falling back to `default`. */
export class RoutedGenerator implements ClaimProducer {
  readonly label = 'routed';

  constructor(
    private readonly producers: Record<string, ClaimProducer>,
    private readonly routes: Record<string, string>,
    private readonly defaultProvider = 'ollama',
  ) {
    if (!(defaultProvider in producers)) throw new Error(`default provider '${defaultProvider}' has no producer`);
  }

  providerFor(domain: string): string {
    const provider = this.routes[domain] ?? this.defaultProvider;
    return provider in this.producers ? provider : this.defaultProvider;
  }

  async produce(args: {
    snapshot: Record<string, any>;
    query: string;
    domain: string;
    feedback?: string | null;
  }): Promise<ActionClaim> {
    return this.producers[this.providerFor(args.domain)].produce(args);
  }
}
