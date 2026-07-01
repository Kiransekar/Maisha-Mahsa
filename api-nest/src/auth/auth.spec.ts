import {
  verifyPassword,
  sign,
  validCookie,
  isPublic,
  assertProductionSecrets,
  DEFAULT_PASSWORD,
} from './auth';

describe('auth (single-user HMAC)', () => {
  it('password + cookie round-trip', () => {
    expect(verifyPassword('hunter2', 'hunter2')).toBe(true);
    expect(verifyPassword('hunter2', 'hunter3')).toBe(false);
    const s = 'secret';
    expect(validCookie(sign(s), s)).toBe(true);
    expect(validCookie(sign('other'), s)).toBe(false);
    expect(validCookie(null, s)).toBe(false);
  });

  it('public allowlist', () => {
    expect(isPublic('/health')).toBe(true);
    expect(isPublic('/health/mahsa')).toBe(true);
    expect(isPublic('/login')).toBe(true);
    expect(isPublic('/docs')).toBe(true);
    expect(isPublic('/api/gst/gstr3b')).toBe(false);
  });

  it('production refuses default secrets', () => {
    expect(() =>
      assertProductionSecrets({
        environment: 'development',
        appPassword: DEFAULT_PASSWORD,
        sessionSecret: 'x',
      }),
    ).not.toThrow();
    expect(() =>
      assertProductionSecrets({
        environment: 'production',
        appPassword: DEFAULT_PASSWORD,
        sessionSecret: 'x',
      }),
    ).toThrow(/default secrets/);
  });
});
