import { composeBrief, briefPayload, DomainHealth } from './cfo';

const h = (domain: string, score: number | null, status: string, approval = false): DomainHealth => ({
  domain,
  score,
  status,
  requires_approval: approval,
  banners: [],
});

describe('cfo.composeBrief', () => {
  const health = [h('gst', 90, 'green'), h('tax', 40, 'red', true), h('ledger', 70, 'yellow')];
  const brief = composeBrief('2024-05-01', health);

  it('averages scored domains', () => {
    expect(brief.overall_score).toBe(66.7); // (90+40+70)/3
  });
  it('orders worst-first and flags attention + approvals', () => {
    expect(brief.scorecard.map((x) => x.domain)).toEqual(['tax', 'ledger', 'gst']);
    expect(brief.needs_attention.map((x) => x.domain)).toEqual(['tax', 'ledger']);
    expect(brief.approvals_pending.map((x) => x.domain)).toEqual(['tax']);
  });
  it('briefPayload maps color and is JSON-able', () => {
    const p = briefPayload(brief);
    expect(p.scorecard[0]).toMatchObject({ domain: 'tax', status: 'red', color: 'red' });
  });
});
