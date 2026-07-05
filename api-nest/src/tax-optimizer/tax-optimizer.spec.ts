import { OptContext, PLAYBOOKS } from './playbooks';

const baseOrg: OptContext['org'] = { sector: null, msme: false, dpiit: false, hasGstin: true, hasEmployees: true, isCompany: true };
const ctx = (facts: Record<string, any>, org: Partial<OptContext['org']> = {}): OptContext => ({
  facts,
  appetite: 'medium',
  org: { ...baseOrg, ...org },
});
const pb = (id: string) => PLAYBOOKS.find((p) => p.id === id)!;

describe('tax playbooks — deterministic, cited, honest', () => {
  it('every playbook carries a statute + section (no advice without a citation)', () => {
    for (const p of PLAYBOOKS) {
      expect(p.statute.length).toBeGreaterThan(0);
      expect(p.section.length).toBeGreaterThan(0);
    }
  });

  it('GST late fee is a deterministic ₹ figure from FACTS (₹50/day)', () => {
    const p = pb('GST-LATEFEE');
    expect(p.appliesWhen(ctx({ gstr3b_days_late: 16 }))).toBe(true);
    expect(p.appliesWhen(ctx({ gstr3b_days_late: 0 }))).toBe(false);
    const m = p.evaluate(ctx({ gstr3b_days_late: 16 }));
    expect(m.savingPaise).toBe(16 * 50_00); // 16 days × ₹50 = ₹800 = 80000 paise
    expect(m.needs).toEqual([]);
  });

  it('never fabricates a number: MSME 43B(h) is null + needs when the unpaid amount is absent', () => {
    const p = pb('MSME-43BH');
    expect(p.appliesWhen(ctx({ msme_max_days_unpaid: 60 }))).toBe(true);
    const missing = p.evaluate(ctx({ msme_max_days_unpaid: 60 }));
    expect(missing.savingPaise).toBeNull();
    expect(missing.needs).toContain('msme_unpaid_paise');
    // With the input present it becomes a deterministic figure.
    const present = p.evaluate(ctx({ msme_max_days_unpaid: 60, msme_unpaid_paise: 1_000_000, marginal_rate_pct: 25 }));
    expect(present.savingPaise).toBe(250_000); // 25% of ₹10,000
  });

  it('applies_when gates on the org, not just facts', () => {
    expect(pb('STARTUP-80IAC').appliesWhen(ctx({}, { dpiit: false }))).toBe(false);
    expect(pb('STARTUP-80IAC').appliesWhen(ctx({}, { dpiit: true }))).toBe(true);
    expect(pb('EXPORT-LUT').appliesWhen(ctx({}, { sector: 'SaaS software', hasGstin: true }))).toBe(true);
    expect(pb('PRESUMPTIVE-44AD').appliesWhen(ctx({}, { isCompany: true }))).toBe(false);
  });

  it('applicable-but-unquantified moves are honest (null saving, non-empty needs)', () => {
    for (const p of PLAYBOOKS) {
      const m = p.evaluate(ctx({}));
      if (m.savingPaise === null) expect(m.needs.length).toBeGreaterThan(0);
    }
  });
});
