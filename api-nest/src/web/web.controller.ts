/** Server-rendered premium UI. Reads live domain health through Mahsa; every page is auth-gated. */
import { Body, Controller, Get, Header, NotFoundException, Param, Post } from '@nestjs/common';

import { AuditService } from '../audit/audit.service';
import { briefPayload, collectHealth, composeBrief } from '../cfo/cfo';
import { LoopService } from '../core/loop.service';
import { MahsaError, MahsaService } from '../mahsa/mahsa.service';
import { DomainRegistry } from '../scheduler/registry.service';
import { page } from './layout';
import { askFragment, auditBody, domainBody, loginBody, overviewBody } from './pages';

const HTML = 'text/html; charset=utf-8';
const today = () => new Date().toISOString().slice(0, 10);

function mahsaDown(msg: string): string {
  return `<div class="page-h"><h1>Overview</h1></div>
    <section class="card verdict" style="margin-top:16px">
      <span class="led" style="color:var(--amber);background:var(--amber)"></span>
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
      return page({ title: 'Overview', body: overviewBody(brief), active: '/' });
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
      return page({ title: domain, body: domainBody(domain, snapshot, fold), active: '/' });
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

  @Get('audit')
  @Header('Content-Type', HTML)
  async auditView(): Promise<string> {
    const entries = await this.audit.loadChain();
    const intact = await this.audit.verify();
    return page({ title: 'Audit', body: auditBody(entries, intact), active: '/audit' });
  }
}
