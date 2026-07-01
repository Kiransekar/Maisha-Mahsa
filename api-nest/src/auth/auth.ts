/**
 * Single-user authentication + secret hardening. Faithful port of api/app/core/auth.py.
 * One operator, one password (MAISHA_APP_PASSWORD), authenticated by a stdlib-HMAC-signed
 * cookie — no session store, no extra dependency. ponytail: swap in a users table + scrypt
 * only if this ever becomes multi-user.
 */
import { createHmac, timingSafeEqual } from 'crypto';

export const COOKIE_NAME = 'maisha_auth';
export const DEFAULT_PASSWORD = 'change-me';
export const DEFAULT_SESSION_SECRET = 'dev-insecure-session-secret-change-me';

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

/** Opaque session token: HMAC(secret, 'authed'). Rotating the secret logs everyone out. */
export function sign(secret: string): string {
  return createHmac('sha256', secret).update('authed').digest('hex');
}

export function validCookie(value: string | null | undefined, secret: string): boolean {
  return value != null && safeEqual(value, sign(secret));
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
