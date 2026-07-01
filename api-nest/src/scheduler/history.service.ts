/**
 * Snapshot history for trend charts. Faithful port of api/app/core/history_store.py. `capture`
 * writes one row per scalar fact per domain at a point in time; `domainSeries` reads them back
 * chronologically. Observability only (never money-math input), so floats are fine.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

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
    if (rows.length) await this.repo.save(rows);
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
