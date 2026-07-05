/**
 * Single-user authentication + secret hardening. Faithful port of api/app/core/auth.py.
 * One operator, one password (MAISHA_APP_PASSWORD), authenticated by a stdlib-HMAC-signed
 * cookie — no session store, no extra dependency. ponytail: swap in a users table + scrypt
 * only if this ever becomes multi-user.
 */
import { createHmac, randomBytes, timingSafeEqual } from 'crypto';

export const COOKIE_NAME = 'maisha_auth';
export const DEFAULT_PASSWORD = 'change-me';
export const DEFAULT_SESSION_SECRET = 'dev-insecure-session-secret-change-me';

/** Session lifetime; a leaked cookie is useless past this window. */
export const SESSION_TTL_MS = Number(process.env.MAISHA_SESSION_TTL_HOURS ?? 168) * 3_600_000;

/** Constant-time equality that never leaks length via early return. */
function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) {
    // Compare against self to keep timing uniform, then fail.
    timingSafeEqual(ab, ab);
    return false;
  }
  return timingSafeEqual(ab, bb);
}

export function verifyPassword(supplied: string, expected: string): boolean {
  return safeEqual(supplied, expected);
}

/**
 * Signed session token: `issuedAt.nonce.HMAC(secret, "issuedAt.nonce")`. The per-mint nonce and
 * issued-at bound a leaked cookie to SESSION_TTL_MS; rotating the secret still logs everyone out.
 */
export function sign(secret: string, iat: number = Date.now(), nonce: string = randomBytes(9).toString('hex')): string {
  const payload = `${iat}.${nonce}`;
  return `${payload}.${createHmac('sha256', secret).update(payload).digest('hex')}`;
}

export function validCookie(value: string | null | undefined, secret: string, now: number = Date.now()): boolean {
  if (value == null) return false;
  const i = value.lastIndexOf('.');
  if (i < 0) return false;
  const payload = value.slice(0, i);
  const mac = value.slice(i + 1);
  const expected = createHmac('sha256', secret).update(payload).digest('hex');
  if (!safeEqual(mac, expected)) return false;
  const iat = Number(payload.split('.')[0]);
  // Reject expired tokens (and tokens dated in the future, allowing 60s of clock skew).
  return Number.isFinite(iat) && now - iat <= SESSION_TTL_MS && iat <= now + 60_000;
}

/** Routes reachable without logging in. */
export function isPublic(path: string): boolean {
  return (
    path === '/health' ||
    path.startsWith('/health/') ||
    path.startsWith('/login') ||
    path.startsWith('/docs')
  );
}

/** Refuse to boot in production with the shipped default secrets (P1-SECRETS). */
export function assertProductionSecrets(args: {
  environment: string;
  appPassword: string;
  sessionSecret: string;
}): void {
  if (args.environment !== 'production') return;
  const bad: string[] = [];
  if (args.appPassword === DEFAULT_PASSWORD) bad.push('MAISHA_APP_PASSWORD');
  if (args.sessionSecret === DEFAULT_SESSION_SECRET) bad.push('MAISHA_SESSION_SECRET');
  if (bad.length) {
    throw new Error(
      `Refusing to start in production with default secrets: ${bad.join(', ')}. ` +
        'Set them in the environment (see .env.example).',
    );
  }
}
