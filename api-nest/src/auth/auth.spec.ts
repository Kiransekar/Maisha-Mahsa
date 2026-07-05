import {
  assertProductionSecrets,
  DEFAULT_PASSWORD,
  hashPassword,
  isPublic,
  normalizeRole,
  signSession,
  verifyPasswordHash,
  verifyPassword,
  verifySession,
  verifyTotp,
} from './auth';

describe('auth — password hashing', () => {
  it('scrypt round-trips and rejects wrong password / tampered hash', () => {
    const h = hashPassword('hunter2-strong');
    expect(verifyPasswordHash('hunter2-strong', h)).toBe(true);
    expect(verifyPasswordHash('wrong', h)).toBe(false);
    expect(verifyPasswordHash('hunter2-strong', 'garbage')).toBe(false);
  });
  it('break-glass constant-time compare still works', () => {
    expect(verifyPassword('x', 'x')).toBe(true);
    expect(verifyPassword('x', 'y')).toBe(false);
  });
});

describe('auth — session claims', () => {
  const secret = 'session-secret';
  it('carries sub + role and round-trips', () => {
    const t = signSession(secret, { sub: 'u1', role: 'operator' });
    const c = verifySession(t, secret);
    expect(c).toMatchObject({ sub: 'u1', role: 'operator' });
  });
  it('rejects wrong secret, tampering, expiry, and future-dated tokens', () => {
    const now = 1_000_000_000_000;
    const t = signSession(secret, { sub: 'u1', role: 'admin' }, now);
    expect(verifySession(t, 'other', now)).toBeNull();
    expect(verifySession(t + 'x', secret, now)).toBeNull();
    expect(verifySession(t, secret, now + 200 * 3_600_000)).toBeNull(); // past 168h TTL
    expect(verifySession(t, secret, now - 10 * 60_000)).toBeNull(); // dated in the future
    expect(verifySession(null, secret, now)).toBeNull();
  });
  it('normalizes legacy/unknown roles', () => {
    expect(normalizeRole('founder')).toBe('admin');
    expect(normalizeRole('operator')).toBe('operator');
    expect(normalizeRole('nonsense')).toBe('viewer');
  });
});

describe('auth — TOTP (RFC 6238)', () => {
  // RFC 6238 test vector: ASCII secret "12345678901234567890" (base32 below), T=59s → SHA1 code 287082.
  const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
  it('accepts the RFC vector and the ±1 step window', () => {
    expect(verifyTotp(secret, '287082', 59_000)).toBe(true);
    expect(verifyTotp(secret, '287082', 59_000 + 30_000)).toBe(true); // next step, within +1 skew
  });
  it('rejects wrong and malformed codes', () => {
    expect(verifyTotp(secret, '000000', 59_000)).toBe(false);
    expect(verifyTotp(secret, 'abc', 59_000)).toBe(false);
    expect(verifyTotp(secret, '287082', 59_000 + 5 * 30_000)).toBe(false); // far out of window
  });
});

describe('auth — routing + secrets', () => {
  it('public allowlist', () => {
    expect(isPublic('/health')).toBe(true);
    expect(isPublic('/login')).toBe(true);
    expect(isPublic('/metrics')).toBe(true);
    expect(isPublic('/api/gst/gstr3b')).toBe(false);
  });
  it('production refuses default secrets', () => {
    expect(() => assertProductionSecrets({ environment: 'development', appPassword: DEFAULT_PASSWORD, sessionSecret: 'x' })).not.toThrow();
    expect(() => assertProductionSecrets({ environment: 'production', appPassword: DEFAULT_PASSWORD, sessionSecret: 'x' })).toThrow(/default secrets/);
  });
});
