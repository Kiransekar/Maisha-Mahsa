/**
 * Scheduled jobs (PRD Layer 6). Faithful port of api/app/jobs.py. Each job is wired for DI so it
 * unit-tests with an in-memory DB, a fake Mahsa, and InMemoryTransport. `runOnce` runs one
 * command (capture|brief|dunning|alerts|audit-verify|all) and never throws — a scheduler tick
 * must not crash the loop; failures are caught and reported per-job.
 */
import { Injectable, Logger } from '@nestjs/common';

import { AuditService } from '../audit/audit.service';
import { collectHealth, composeBrief, briefPayload } from '../cfo/cfo';
import { composeComplianceAlert, composeDunning } from '../email/compose';
import { EmailChannel } from '../email/channel';
import { MahsaError, MahsaService } from '../mahsa/mahsa.service';
import { MemoryService } from '../memory/memory.service';
import { DomainRegistry } from './registry.service';
import { HistoryService } from './history.service';

// Minimal surfaces we pull off the registry without importing the domain modules.
interface HasAlerts {
  alerts(asOf: string): Promise<Record<string, any>[]>;
}
interface HasDunning {
  pendingDunning(asOf: string): Promise<Record<string, any>[]>;
}

export type JobCommand = 'capture' | 'brief' | 'dunning' | 'alerts' | 'audit-verify' | 'evolve' | 'all';

@Injectable()
export class JobsService {
  private readonly log = new Logger('maisha.jobs');

  constructor(
    private readonly registry: DomainRegistry,
    private readonly history: HistoryService,
    private readonly mahsa: MahsaService,
    private readonly audit: AuditService,
    private readonly channel: EmailChannel,
    private readonly memory: MemoryService,
  ) {}

  /** Offline memory evolution: consolidate the hot layer + cap the archive (survey §5.2/§7.8). */
  async runEvolve(): Promise<Record<string, any>> {
    return this.memory.evolve();
  }

  private cfoEmail(): string {
    return process.env.MAISHA_CFO_EMAIL ?? 'founder@maisha-mahsa.local';
  }
  private companyName(): string {
    return process.env.MAISHA_APP_NAME ?? 'Maisha-Mahsa';
  }

  async runCapture(capturedAt: string, asOf: string): Promise<Record<string, any>> {
    const metrics = await this.history.capture(capturedAt, asOf);
    return { job: 'capture', captured_at: capturedAt, metrics };
  }

  async runBrief(asOf: string): Promise<Record<string, any>> {
    const health = await collectHealth(this.registry.all(), this.mahsa, asOf);
    const brief = composeBrief(asOf, health);
    await this.channel.sendDailyBrief(this.cfoEmail(), briefPayload(brief), this.companyName());
    return { job: 'brief', to: this.cfoEmail(), needs_attention: brief.needs_attention.length, overall_score: brief.overall_score };
  }

  async runAlerts(asOf: string): Promise<Record<string, any>> {
    const compliance = this.registry.get('compliance') as unknown as HasAlerts | undefined;
    const alerts = compliance ? await compliance.alerts(asOf) : [];
    if (alerts.length === 0) return { job: 'alerts', dispatched: 0 };
    await this.channel.sendComplianceAlert(this.cfoEmail(), composeComplianceAlert(alerts, asOf));
    return { job: 'alerts', dispatched: alerts.length };
  }

  async runDunning(asOf: string): Promise<Record<string, any>> {
    const revenue = this.registry.get('revenue') as unknown as HasDunning | undefined;
    const pending = revenue ? await revenue.pendingDunning(asOf) : [];
    let sent = 0;
    for (const item of pending) {
      const to = item.customer_email || this.cfoEmail();
      await this.channel.sendDunning(to, composeDunning(item, asOf), this.companyName());
      sent += 1;
    }
    return { job: 'dunning', dispatched: sent };
  }

  async runAuditVerify(): Promise<Record<string, any>> {
    const chain = await this.audit.loadChain();
    const intact = await this.audit.verify();
    if (!intact) this.log.error(`AUDIT CHAIN INTEGRITY FAILURE — ${chain.length} entries, chain broken`);
    return { job: 'audit_verify', intact, entries: chain.length };
  }

  /** Run a command once. Failures are caught and reported per-job, never thrown. */
  async runOnce(command: JobCommand, asOf: string): Promise<Record<string, any>> {
    const today = asOf;
    const results: Record<string, any>[] = [];
    const guard = async (job: string, fn: () => Promise<Record<string, any>>) => {
      try {
        results.push(await fn());
      } catch (e) {
        const msg = (e as Error).message;
        if (e instanceof MahsaError) this.log.warn(`${job} job skipped: ${msg}`);
        else this.log.error(`${job} job failed: ${msg}`);
        results.push({ job, error: msg });
      }
    };

    if (command === 'capture' || command === 'all') await guard('capture', () => this.runCapture(today, today));
    if (command === 'brief' || command === 'all') await guard('brief', () => this.runBrief(today));
    if (command === 'dunning' || command === 'all') await guard('dunning', () => this.runDunning(today));
    if (command === 'alerts' || command === 'all') await guard('alerts', () => this.runAlerts(today));
    if (command === 'audit-verify' || command === 'all') await guard('audit_verify', () => this.runAuditVerify());
    if (command === 'evolve' || command === 'all') await guard('evolve', () => this.runEvolve());

    return { ran: command, at: new Date().toISOString(), results };
  }
}
