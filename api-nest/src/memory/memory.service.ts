/**
 * The semantic hot layer — the CFO Profile that makes Maisha know *this* organization.
 *
 * Two blocks per org, injected into the drafting prompt every turn:
 *   ORG  — derived live from the `company` row (never stale).
 *   CFO  — the agent's learned, hard-capped posture/preferences (durable facts only).
 *
 * The Golden-Rule memory law: this layer stores facts, preferences and posture — NEVER a computed
 * rupee figure. Numbers always come from FACTS/Mahsa at inference. The char cap is a feature: it
 * forces durable-facts-only and rejects a write that would overflow (Hermes' discipline).
 */
import { BadRequestException, Injectable, Optional } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { AuditService } from '../audit/audit.service';
import { currentUserId } from '../auth/request-context';
import { Company } from '../common/shared.entities';
import { OrgMemory, OrgMemoryHistory } from './org-memory.entities';

export const CFO_CHAR_LIMIT = 2200; // model-agnostic (chars, not tokens); Hermes default

/** Deterministic consolidation: trim, drop empties, and dedupe lines (first occurrence wins). */
export function consolidate(content: string): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of content.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const key = line.toLowerCase().replace(/^[-*•]\s*/, '');
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out.join('\n');
}

@Injectable()
export class MemoryService {
  constructor(
    @InjectRepository(OrgMemory) private readonly repo: Repository<OrgMemory>,
    @InjectRepository(OrgMemoryHistory) private readonly history: Repository<OrgMemoryHistory>,
    @InjectRepository(Company) private readonly companies: Repository<Company>,
    @Optional() private readonly audit?: AuditService,
  ) {}

  private async resolveCompanyId(companyId?: number): Promise<number> {
    if (companyId != null) return companyId;
    const c = await this.companies.findOne({ where: {}, order: { id: 'ASC' } });
    return c?.id ?? 1;
  }

  /** The learned CFO block for an org, with its char budget. */
  async getCfo(companyId?: number): Promise<{ content: string; used: number; limit: number }> {
    const cid = await this.resolveCompanyId(companyId);
    const row = await this.repo.findOne({ where: { company_id: cid, kind: 'cfo' } });
    const content = row?.content ?? '';
    return { content, used: content.length, limit: CFO_CHAR_LIMIT };
  }

  /**
   * Replace the CFO block. Consolidates (dedupes) first; rejects (never truncates) when still over
   * budget — forces the human to prune. Soft/temporal update (survey §5.2): the prior version is
   * archived, not overwritten, and the change is sealed into the audit chain (auditable updates §7.7).
   */
  async setCfo(content: string, companyId?: number): Promise<{ content: string; used: number; limit: number }> {
    const next = consolidate(content);
    if (next.length > CFO_CHAR_LIMIT) {
      throw new BadRequestException(
        `CFO memory is ${next.length} chars after consolidation; the limit is ${CFO_CHAR_LIMIT}. ` +
          'Remove or shorten a line to make room (durable facts only).',
      );
    }
    const cid = await this.resolveCompanyId(companyId);
    const current = await this.repo.findOne({ where: { company_id: cid, kind: 'cfo' } });
    if (current && current.content && current.content !== next) {
      // Non-destructive: keep the superseded version rather than overwriting it.
      await this.history.save(this.history.create({ company_id: cid, kind: 'cfo', content: current.content, superseded_at: new Date().toISOString() }));
    }
    await this.repo.upsert({ company_id: cid, kind: 'cfo', content: next }, ['company_id', 'kind']);
    if (this.audit && (!current || current.content !== next)) {
      await this.audit
        .append({
          timestamp: new Date().toISOString(),
          action: 'memory.update',
          domain: 'memory',
          user_id: currentUserId(),
          query: null,
          intent_global: null,
          intent_domain: null,
          validation_status: 'recorded',
          rules_version: 'memory/v1',
        })
        .catch(() => undefined); // best-effort: a memory write must not fail on an audit hiccup
    }
    return { content: next, used: next.length, limit: CFO_CHAR_LIMIT };
  }

  /**
   * Offline evolution (survey §5.2/§7.8): re-consolidate the active hot layer and cap the archive to
   * a bounded retention window. Runs on the scheduler, out of band. Non-destructive to active memory.
   */
  async evolve(companyId?: number, keepVersions = 20): Promise<{ consolidated: boolean; history_pruned: number }> {
    const cid = await this.resolveCompanyId(companyId);
    const cur = await this.repo.findOne({ where: { company_id: cid, kind: 'cfo' } });
    let consolidated = false;
    if (cur?.content) {
      const deduped = consolidate(cur.content);
      if (deduped !== cur.content) {
        await this.setCfo(deduped, cid); // archives + seals the consolidation as an auditable update
        consolidated = true;
      }
    }
    const rows = await this.history.find({ where: { company_id: cid, kind: 'cfo' }, order: { id: 'DESC' } });
    let history_pruned = 0;
    if (rows.length > keepVersions) {
      const drop = rows.slice(keepVersions).map((r) => r.id);
      await this.history.delete(drop);
      history_pruned = drop.length;
    }
    return { consolidated, history_pruned };
  }

  /** Superseded versions, newest first — non-destructive history of the hot layer. */
  async getHistory(companyId?: number): Promise<Array<{ content: string; superseded_at: string }>> {
    const cid = await this.resolveCompanyId(companyId);
    const rows = await this.history.find({ where: { company_id: cid, kind: 'cfo' }, order: { id: 'DESC' }, take: 50 });
    return rows.map((r) => ({ content: r.content, superseded_at: r.superseded_at }));
  }

  /** Append one durable line; rejects on overflow so the hot layer never becomes a dumping ground. */
  async appendCfo(line: string, companyId?: number): Promise<{ content: string; used: number; limit: number }> {
    const { content } = await this.getCfo(companyId);
    const clean = line.trim().replace(/\n+/g, ' ');
    const next = content ? `${content}\n- ${clean}` : `- ${clean}`;
    return this.setCfo(next, companyId);
  }

  /** ORG block, derived live from the company record (so it can never go stale). */
  renderOrg(c: Company): string {
    const lines: string[] = [`${c.name}`];
    if (c.sector) lines.push(`sector: ${c.sector}`);
    if (c.state) lines.push(`state: ${c.state}`);
    if (c.pan) lines.push(`PAN: ${c.pan}`);
    if (c.gstin) lines.push(`GSTIN: ${c.gstin}`);
    if (c.incorporation_date) lines.push(`incorporated: ${c.incorporation_date}`);
    lines.push(`FY ends: ${c.financial_year_end}`);
    if (c.msme_registration) lines.push(`MSME: ${c.msme_registration}`);
    if (c.dpiit_recognition) lines.push(`DPIIT recognised: ${c.dpiit_recognition}`);
    return lines.join(' · ');
  }

  /** The full profile text for prompt injection (empty-safe). Context only — never a source of numbers. */
  async profileText(companyId?: number): Promise<string> {
    const cid = await this.resolveCompanyId(companyId);
    const company = await this.companies.findOne({ where: { id: cid } });
    const org = company ? this.renderOrg(company) : '';
    const { content: cfo } = await this.getCfo(cid);
    const blocks: string[] = [];
    if (org) blocks.push(`ORG:\n  ${org}`);
    if (cfo) blocks.push(`CFO POSTURE (durable preferences — context only, NEVER a source of numbers):\n${cfo}`);
    return blocks.join('\n\n');
  }
}
