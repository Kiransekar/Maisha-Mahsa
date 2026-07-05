/**
 * Snapshot history for trend charts. Faithful port of api/app/core/history_store.py. `capture`
 * writes one row per scalar fact per domain at a point in time; `domainSeries` reads them back
 * chronologically. Observability only (never money-math input), so floats are fine.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { LessThan, Repository } from 'typeorm';

/** Trend history is capped at this many days; older captures are pruned to bound table growth. */
const RETENTION_DAYS = Number(process.env.MAISHA_HISTORY_RETENTION_DAYS ?? 400);

import { MetricSnapshot } from '../common/shared.entities';
import { enrich } from '../llm/tools';
import { DomainRegistry } from './registry.service';

function numeric(value: unknown): number | null {
  if (typeof value === 'boolean') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
}

@Injectable()
export class HistoryService {
  constructor(
    @InjectRepository(MetricSnapshot) private readonly repo: Repository<MetricSnapshot>,
    private readonly registry: DomainRegistry,
  ) {}

  /** Capture every domain's current numeric facts. Returns the number of rows written. */
  async capture(capturedAt: string, asOf?: string): Promise<number> {
    const rows: MetricSnapshot[] = [];
    for (const service of this.registry.all()) {
      const facts = enrich(await service.buildSnapshot(asOf));
      for (const [metric, raw] of Object.entries(facts)) {
        if (metric === 'as_of') continue;
        const value = numeric(raw);
        if (value === null) continue;
        rows.push(this.repo.create({ captured_at: capturedAt, domain: service.domain, metric, value }));
      }
    }
    // Idempotent per (domain, captured_at, metric): a re-run on the same day overwrites, never
    // duplicates — duplicate rows would corrupt every trend series.
    if (rows.length) await this.repo.upsert(rows, ['domain', 'captured_at', 'metric']);

    // Prune history older than the retention window (ISO date strings sort chronologically).
    const cutoffMs = Date.parse(`${capturedAt}T00:00:00Z`) - RETENTION_DAYS * 86_400_000;
    if (Number.isFinite(cutoffMs)) {
      await this.repo.delete({ captured_at: LessThan(new Date(cutoffMs).toISOString().slice(0, 10)) });
    }
    return rows.length;
  }

  /** All captured series for a domain: {metric: [[capturedAt, value], …]} chronological. */
  async domainSeries(domain: string): Promise<Record<string, [string, number][]>> {
    const rows = await this.repo.find({ where: { domain }, order: { id: 'ASC' } });
    const out: Record<string, [string, number][]> = {};
    for (const r of rows) (out[r.metric] ??= []).push([r.captured_at, r.value]);
    return out;
  }
}
