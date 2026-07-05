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
import { BadRequestException, Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { Company } from '../common/shared.entities';
import { OrgMemory } from './org-memory.entities';

export const CFO_CHAR_LIMIT = 2200; // model-agnostic (chars, not tokens); Hermes default

@Injectable()
export class MemoryService {
  constructor(
    @InjectRepository(OrgMemory) private readonly repo: Repository<OrgMemory>,
    @InjectRepository(Company) private readonly companies: Repository<Company>,
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

  /** Replace the CFO block. Rejects (does not truncate) when over budget — forces consolidation. */
  async setCfo(content: string, companyId?: number): Promise<{ content: string; used: number; limit: number }> {
    const trimmed = content.trim();
    if (trimmed.length > CFO_CHAR_LIMIT) {
      throw new BadRequestException(
        `CFO memory is ${trimmed.length} chars; the limit is ${CFO_CHAR_LIMIT}. ` +
          'Consolidate — remove or shorten a line to make room (durable facts only).',
      );
    }
    const cid = await this.resolveCompanyId(companyId);
    await this.repo.upsert({ company_id: cid, kind: 'cfo', content: trimmed }, ['company_id', 'kind']);
    return { content: trimmed, used: trimmed.length, limit: CFO_CHAR_LIMIT };
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
