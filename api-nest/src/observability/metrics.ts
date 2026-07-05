/**
 * Minimal Prometheus metrics — no dependency. Enough for enterprise SLO scraping (request rate by
 * method/status, in-flight gauge, latency quantiles, uptime, memory). Swap in prom-client if richer
 * histograms are ever needed.
 */
const counters = new Map<string, number>();
let inflight = 0;
const started = Date.now();
const durations: number[] = [];

export function recordRequest(method: string, status: number, ms: number): void {
  const key = `${method}|${status}`;
  counters.set(key, (counters.get(key) ?? 0) + 1);
  durations.push(ms);
  if (durations.length > 5000) durations.shift();
}

export function incInflight(): void {
  inflight++;
}
export function decInflight(): void {
  inflight = Math.max(0, inflight - 1);
}

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return 0;
  return sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
}

export function renderMetrics(): string {
  const L: string[] = [];
  L.push('# HELP maisha_http_requests_total Total HTTP requests by method and status', '# TYPE maisha_http_requests_total counter');
  for (const [k, v] of counters) {
    const [m, s] = k.split('|');
    L.push(`maisha_http_requests_total{method="${m}",status="${s}"} ${v}`);
  }
  L.push('# HELP maisha_http_inflight In-flight HTTP requests', '# TYPE maisha_http_inflight gauge', `maisha_http_inflight ${inflight}`);
  L.push('# HELP maisha_uptime_seconds Process uptime in seconds', '# TYPE maisha_uptime_seconds gauge', `maisha_uptime_seconds ${Math.floor((Date.now() - started) / 1000)}`);
  const mem = process.memoryUsage();
  L.push('# HELP maisha_process_resident_memory_bytes Resident memory', '# TYPE maisha_process_resident_memory_bytes gauge', `maisha_process_resident_memory_bytes ${mem.rss}`);
  if (durations.length) {
    const sorted = [...durations].sort((a, b) => a - b);
    L.push('# HELP maisha_http_duration_ms Request duration quantiles (ms)', '# TYPE maisha_http_duration_ms summary');
    L.push(`maisha_http_duration_ms{quantile="0.5"} ${quantile(sorted, 0.5)}`);
    L.push(`maisha_http_duration_ms{quantile="0.95"} ${quantile(sorted, 0.95)}`);
    L.push(`maisha_http_duration_ms{quantile="0.99"} ${quantile(sorted, 0.99)}`);
  }
  return L.join('\n') + '\n';
}
