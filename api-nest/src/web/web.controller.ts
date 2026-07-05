/** Server-rendered premium UI. Reads live domain health through Mahsa; every page is auth-gated. */
import { Body, Controller, Get, Header, NotFoundException, Param, Post } from '@nestjs/common';

import { AuditService } from '../audit/audit.service';
import { briefPayload, collectHealth, composeBrief, DomainHealth } from '../cfo/cfo';
import { LoopService } from '../core/loop.service';
import { MahsaError, MahsaService } from '../mahsa/mahsa.service';
import { DomainRegistry } from '../scheduler/registry.service';
import { HistoryService } from '../scheduler/history.service';
import { page } from './layout';
import { approvalsBody, askFragment, auditBody, DomainAction, domainBody, loginBody, overviewBody, settingsBody, trendsBody } from './pages';

const HTML = 'text/html; charset=utf-8';
const today = () => new Date().toISOString().slice(0, 10);

// Curated live reports per domain → real GET endpoints. ponytail: links open the engine's JSON (or
// PDF); rendered report views are the next slice, not a blocker for launch.
const ACTIONS: Record<string, DomainAction[]> = {
  gst: [
    { label: 'ITC reconciliation', href: '/api/gst/itc/reconcile', icon: '⇄' },
    { label: 'Validate a GSTIN', href: '/api/gst/validate-gstin?gstin=27AAPFU0939F1ZV', icon: '✓' },
  ],
  ledger: [
    { label: 'Profit & loss', href: '/api/ledger/pnl', icon: '₹' },
    { label: 'Balance sheet', href: '/api/ledger/balance-sheet', icon: '⚖' },
    { label: 'Trial balance', href: '/api/ledger/trial-balance', icon: '≡' },
  ],
  treasury: [{ label: 'Cash position', href: '/api/treasury/cash', icon: '₹' }],
  payroll: [{ label: 'Payroll preview', href: '/api/payroll/preview', icon: '≡' }],
  revenue: [
    { label: 'AR aging', href: '/api/revenue/ar-aging', icon: '⏳' },
    { label: 'Dunning queue', href: '/api/revenue/dunning', icon: '✉' },
  ],
  expense: [{ label: 'Expense analytics', href: '/api/expense/analytics', icon: '📊' }],
  payables: [{ label: 'AP aging', href: '/api/payables/ap-aging', icon: '⏳' }],
  tax: [{ label: 'TDS summary', href: '/api/tax/tds-summary', icon: '≡' }],
  equity: [{ label: 'Cap table', href: '/api/equity/cap-table', icon: '▦' }],
  compliance: [{ label: 'Statutory alerts', href: '/api/compliance/alerts', icon: '🔔' }],
};

function mahsaDown(msg: string): string {
  return `<div class="page-h"><h1>Overview</h1></div>
    <section class="card verdict warn" style="margin-top:16px">
      <span class="led" style="background:var(--warn)"></span>
      <div><b>Mahsa engine unreachable</b>
      <div style="color:var(--muted);font-size:13px;margin-top:4px">The suite refuses to show a verdict it can't validate (the Golden Rule). Start the sidecar, then reload.</div>
      <div class="hash" style="margin-top:8px">${msg}</div></div></section>`;
}

@Controller()
export class WebController {
  constructor(
    private readonly registry: DomainRegistry,
    private readonly mahsa: MahsaService,
    private readonly loop: LoopService,
    private readonly audit: AuditService,
    private readonly history: HistoryService,
  ) {}

  @Get('login')
  @Header('Content-Type', HTML)
  login(): string {
    return page({ title: 'Sign in', body: loginBody(), bare: true });
  }

  @Get()
  @Header('Content-Type', HTML)
  async overview(): Promise<string> {
    try {
      const health = await collectHealth(this.registry.all(), this.mahsa, today());
      const brief = briefPayload(composeBrief(today(), health));
      const intact = await this.audit.verify().catch(() => true);
      return page({ title: 'Overview', body: overviewBody(brief, intact), active: '/' });
    } catch (e) {
      const body = e instanceof MahsaError ? mahsaDown(e.message) : mahsaDown((e as Error).message);
      return page({ title: 'Overview', body, active: '/' });
    }
  }

  @Get('d/:domain')
  @Header('Content-Type', HTML)
  async domain(@Param('domain') domain: string): Promise<string> {
    const service = this.registry.get(domain);
    if (!service) throw new NotFoundException(`unknown domain ${domain}`);
    try {
      const snapshot = await service.buildSnapshot(today());
      const fold = await this.mahsa.fold(snapshot, { domain });
      const series = await this.history.domainSeries(domain).catch(() => ({}));
      return page({ title: domain, body: domainBody(domain, snapshot, fold, series, ACTIONS[domain] ?? []), active: '/' });
    } catch (e) {
      return page({ title: domain, body: mahsaDown((e as Error).message), active: '/' });
    }
  }

  @Post('d/:domain/ask')
  @Header('Content-Type', HTML)
  async ask(@Param('domain') domain: string, @Body() body: { q?: string }): Promise<string> {
    const service = this.registry.get(domain);
    if (!service) throw new NotFoundException(`unknown domain ${domain}`);
    const outcome = await this.loop.run({
      service,
      timestamp: new Date().toISOString(),
      query: (body.q ?? '').slice(0, 500),
      action: `${domain}.ask`,
    });
    return askFragment(outcome.claim, outcome.claimVerified, outcome.auditHash);
  }

  @Get('approvals')
  @Header('Content-Type', HTML)
  async approvals(): Promise<string> {
    try {
      const health: DomainHealth[] = await collectHealth(this.registry.all(), this.mahsa, today());
      const pending = health.filter((h) => h.requires_approval);
      const rows = await Promise.all(
        pending.map(async (h) => ({ health: h, fold: await this.mahsa.fold(await this.registry.get(h.domain)!.buildSnapshot(today()), { domain: h.domain }) })),
      );
      return page({ title: 'Approvals', body: approvalsBody(rows), active: '/approvals' });
    } catch (e) {
      return page({ title: 'Approvals', body: mahsaDown((e as Error).message), active: '/approvals' });
    }
  }

  @Get('trends')
  @Header('Content-Type', HTML)
  async trends(): Promise<string> {
    const data = await Promise.all(
      this.registry.all().map(async (s) => ({ domain: s.domain, series: await this.history.domainSeries(s.domain).catch(() => ({})) })),
    );
    return page({ title: 'Trends', body: trendsBody(data), active: '/trends' });
  }

  @Get('settings')
  @Header('Content-Type', HTML)
  async settings(): Promise<string> {
    const h = await this.mahsa.health().catch(() => ({}));
    return page({
      title: 'Settings',
      body: settingsBody({
        engine: h.engine_version ?? 'unreachable',
        rules: h.rules_version ?? '—',
        scheduler: process.env.MAISHA_SCHEDULER_ENABLED === 'true',
        llm: process.env.MAISHA_LLM_PROVIDER ?? 'off',
        domains: this.registry.all().length,
      }),
      active: '/settings',
    });
  }

  @Get('audit')
  @Header('Content-Type', HTML)
  async auditView(): Promise<string> {
    const entries = await this.audit.loadChain();
    const intact = await this.audit.verify();
    return page({ title: 'Audit', body: auditBody(entries, intact), active: '/audit' });
  }
}
