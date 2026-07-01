import { GENESIS_HASH, makeEntry, verifyChain, AuditCore, AuditEntry } from './audit';

const core = (n: number): AuditCore => ({
  timestamp: `2024-05-0${n}`,
  action: 'fold',
  domain: 'gst',
  user_id: 'founder',
  query: null,
  intent_global: [0.5, 0.5],
  intent_domain: null,
  validation_status: 'green',
  rules_version: 'v1',
});

describe('audit hash-chain', () => {
  it('links entries and detects tampering', () => {
    const chain: AuditEntry[] = [];
    let prev = GENESIS_HASH;
    for (const n of [1, 2, 3]) {
      const e = makeEntry(prev, core(n));
      chain.push(e);
      prev = e.this_hash;
    }
    expect(verifyChain(chain)).toBe(true);
    const tampered = [...chain];
    tampered[1] = { ...tampered[1], action: 'tampered' };
    expect(verifyChain(tampered)).toBe(false);
  });
});
