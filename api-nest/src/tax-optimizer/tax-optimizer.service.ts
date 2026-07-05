/**
 * The Tax Optimizer — turns the org's real FACTS + its CFO Profile into a ranked, cited, ₹-quantified
 * list of tax-saving moves. Every rupee figure is computed deterministically by a playbook (same
 * trust level as the domain calc engines), never by an LLM (the Golden Rule); each run is sealed
 * into the hash-chained audit log. Personalized by the CFO Profile's risk appetite.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { AuditService } from '../audit/audit.service';
import { Company } from '../common/shared.entities';
import { formatInr } from '../common/money';
import { MemoryService } from '../memory/memory.service';
import { DomainRegistry } from '../scheduler/registry.service';
import { FactVal, Move, OptContext, PLAYBOOKS, Playbook } from './playbooks';

const RISK_PRIORITY: Record<string, number> = { low: 3, medium: 2, aggressive: 1 };

export interface OptimizerMove {
  id: string;
  name: string;
  category: string;
  statute: string;
  section: string;
  risk: string;
  saving_paise: number | null;
  saving_inr: string | null;
  needs: string[];
  note: string;
  steps: string[];
}

export interface OptimizationReport {
  as_of: string;
  appetite: string;
  org: OptContext['org'];
  quantified_saving_paise: number;
  quantified_saving_inr: string;
  moves: OptimizerMove[];
  audit_hash: string;
}

@Injectable()
export class TaxOptimizerService {
  constructor(
    private readonly registry: DomainRegistry,
    private readonly memory: MemoryService,
    private readonly audit: AuditService,
    @InjectRepository(Company) private readonly companies: Repository<Company>,
  ) {}

  /** Merge every domain's deterministic snapshot metrics into one flat FACTS map. */
  private async gatherFacts(asOf?: string): Promise<Record<string, FactVal>> {
    const facts: Record<string, FactVal> = {};
    for (const service of this.registry.all()) {
      const snap = await service.buildSnapshot(asOf).catch(() => ({}) as Record<string, any>);
      const metrics = (snap.metrics ?? {}) as Record<string, unknown>;
      for (const [k, v] of Object.entries({ ...snap, ...metrics })) {
        if (k === 'metrics' || k === 'as_of') continue;
        if (typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean') facts[k] = v;
      }
    }
    return facts;
  }

  private detectAppetite(cfo: string): 'low' | 'medium' | 'aggressive' {
    const t = cfo.toLowerCase();
    if (/aggressive|maximis|maximize|risk[- ]?tolerant/.test(t)) return 'aggressive';
    if (/conservative|cautious|low[- ]?risk|risk[- ]?averse/.test(t)) return 'low';
    return 'medium';
  }

  async optimize(asOf?: string): Promise<OptimizationReport> {
    const as_of = asOf ?? new Date().toISOString().slice(0, 10);
    const facts = await this.gatherFacts(asOf);
    const company = await this.companies.findOne({ where: {}, order: { id: 'ASC' } });
    const { content: cfo } = await this.memory.getCfo();
    const appetite = this.detectAppetite(cfo);

    const ctx: OptContext = {
      facts,
      appetite,
      org: {
        sector: company?.sector ?? null,
        msme: !!company?.msme_registration,
        dpiit: !!company?.dpiit_recognition,
        hasGstin: !!company?.gstin,
        hasEmployees: (typeof facts.employee_count === 'number' ? facts.employee_count : 0) > 0,
        isCompany: !!company?.cin, // CIN present ⇒ incorporated company; else LLP/proprietor
      },
    };

    const applicable = PLAYBOOKS.filter((p) => safe(() => p.appliesWhen(ctx), false)).filter(
      (p) => appetite !== 'low' || p.risk !== 'aggressive',
    );

    const moves: OptimizerMove[] = applicable
      .map((p) => {
        const m: Move = safe(() => p.evaluate(ctx), { savingPaise: null, needs: [], note: '' });
        return {
          id: p.id,
          name: p.name,
          category: p.category,
          statute: p.statute,
          section: p.section,
          risk: p.risk,
          saving_paise: m.savingPaise,
          saving_inr: m.savingPaise == null ? null : formatInr(m.savingPaise),
          needs: m.needs,
          note: m.note,
          steps: p.steps,
        };
      })
      .sort(rankMoves);

    const quantified = moves.reduce((s, m) => s + (m.saving_paise ?? 0), 0);

    // Seal the advisory run into the audit chain — deterministic, tamper-evident, no LLM number.
    const entry = await this.audit.append({
      timestamp: new Date().toISOString(),
      action: 'tax.optimize',
      domain: 'tax',
      user_id: process.env.MAISHA_DEFAULT_USER_ID ?? 'founder',
      query: null,
      intent_global: null,
      intent_domain: null,
      validation_status: 'advisory',
      rules_version: 'tax-optimizer/v1',
    });

    return {
      as_of,
      appetite,
      org: ctx.org,
      quantified_saving_paise: quantified,
      quantified_saving_inr: formatInr(quantified),
      moves,
      audit_hash: entry.this_hash,
    };
  }
}

/** Quantified moves first (largest ₹ saving), then applicable-but-needs-input by risk priority. */
function rankMoves(a: OptimizerMove, b: OptimizerMove): number {
  const aq = a.saving_paise != null,
    bq = b.saving_paise != null;
  if (aq !== bq) return aq ? -1 : 1;
  if (aq && bq) return (b.saving_paise ?? 0) - (a.saving_paise ?? 0);
  return (RISK_PRIORITY[b.risk] ?? 0) - (RISK_PRIORITY[a.risk] ?? 0) || a.name.localeCompare(b.name);
}

function safe<T>(fn: () => T, fallback: T): T {
  try {
    return fn();
  } catch {
    return fallback;
  }
}
