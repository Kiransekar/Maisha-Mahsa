/**
 * Enterprise authentication primitives (stdlib only — no bcrypt/otp dependency).
 *  - password hashing: scrypt with a per-user salt.
 *  - sessions: an HMAC-signed, claims-carrying cookie ({sub, role, iat, nonce}) with a TTL.
 *  - MFA: RFC-6238 TOTP (HMAC-SHA1) verified with ±1 step skew.
 *  - RBAC roles: admin ⊃ operator (writers) ⊃ viewer (read-only).
 * A break-glass bootstrap admin (MAISHA_APP_PASSWORD) keeps the system reachable before users exist.
 */
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from 'crypto';

export const COOKIE_NAME = 'maisha_auth';
export const DEFAULT_PASSWORD = 'change-me';
export const DEFAULT_SESSION_SECRET = 'dev-insecure-session-secret-change-me';

/** Session lifetime; a leaked cookie is useless past this window. */
export const SESSION_TTL_MS = Number(process.env.MAISHA_SESSION_TTL_HOURS ?? 168) * 3_600_000;

export const ROLES = ['admin', 'operator', 'viewer'] as const;
export type Role = (typeof ROLES)[number];
export const WRITER_ROLES: readonly Role[] = ['admin', 'operator'];
/** Legacy 'founder' role → admin. */
export const normalizeRole = (r: string): Role => (r === 'founder' ? 'admin' : (ROLES as readonly string[]).includes(r) ? (r as Role) : 'viewer');

/** Constant-time equality that never leaks length via early return. */
function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) {
    timingSafeEqual(ab, ab);
    return false;
  }
  return timingSafeEqual(ab, bb);
}

/** Constant-time compare of a plaintext against the break-glass env password. */
export function verifyPassword(supplied: string, expected: string): boolean {
  return safeEqual(supplied, expected);
}

// ---- password hashing (scrypt) --------------------------------------------------------

export function hashPassword(pw: string): string {
  const salt = randomBytes(16);
  return `${salt.toString('hex')}:${scryptSync(pw, salt, 64).toString('hex')}`;
}

export function verifyPasswordHash(pw: string, stored: string): boolean {
  const [saltHex, hHex] = (stored ?? '').split(':');
  if (!saltHex || !hHex) return false;
  return safeEqual(scryptSync(pw, Buffer.from(saltHex, 'hex'), 64).toString('hex'), hHex);
}

// ---- session tokens (claims-carrying) -------------------------------------------------

export interface Claims {
  sub: string; // user id (or 'bootstrap')
  role: Role;
  iat: number;
}

export function signSession(secret: string, claims: { sub: string; role: Role }, iat: number = Date.now(), nonce: string = randomBytes(9).toString('hex')): string {
  const body = Buffer.from(JSON.stringify({ ...claims, iat, n: nonce })).toString('base64url');
  return `${body}.${createHmac('sha256', secret).update(body).digest('hex')}`;
}

export function verifySession(value: string | null | undefined, secret: string, now: number = Date.now()): Claims | null {
  if (!value) return null;
  const i = value.lastIndexOf('.');
  if (i < 0) return null;
  const body = value.slice(0, i);
  const mac = value.slice(i + 1);
  if (!safeEqual(createHmac('sha256', secret).update(body).digest('hex'), mac)) return null;
  let p: any;
  try {
    p = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
  } catch {
    return null;
  }
  if (!p || typeof p.iat !== 'number' || typeof p.sub !== 'string') return null;
  // Reject expired tokens (and tokens dated in the future, allowing 60s of clock skew).
  if (now - p.iat > SESSION_TTL_MS || p.iat > now + 60_000) return null;
  return { sub: String(p.sub), role: normalizeRole(String(p.role)), iat: p.iat };
}

// ---- MFA: RFC-6238 TOTP (HMAC-SHA1) ---------------------------------------------------

const B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

export function randomTotpSecret(): string {
  const buf = randomBytes(20);
  let bits = 0,
    val = 0,
    out = '';
  for (const b of buf) {
    val = (val << 8) | b;
    bits += 8;
    while (bits >= 5) {
      out += B32[(val >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  return out;
}

function b32decode(s: string): Buffer {
  const clean = s.replace(/=+$/, '').toUpperCase();
  let bits = 0,
    val = 0;
  const out: number[] = [];
  for (const c of clean) {
    const idx = B32.indexOf(c);
    if (idx < 0) continue;
    val = (val << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((val >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

function hotp(secret: Buffer, counter: number): string {
  const buf = Buffer.alloc(8);
  let c = counter;
  for (let i = 7; i >= 0; i--) {
    buf[i] = c & 0xff;
    c = Math.floor(c / 256);
  }
  const h = createHmac('sha1', secret).update(buf).digest();
  const off = h[h.length - 1] & 0xf;
  const bin = ((h[off] & 0x7f) << 24) | ((h[off + 1] & 0xff) << 16) | ((h[off + 2] & 0xff) << 8) | (h[off + 3] & 0xff);
  return String(bin % 1_000_000).padStart(6, '0');
}

/** Verify a 6-digit TOTP against a base32 secret, tolerating ±1 30s step of clock skew. */
export function verifyTotp(secretB32: string, token: string, now: number = Date.now()): boolean {
  if (!/^\d{6}$/.test((token ?? '').trim())) return false;
  const secret = b32decode(secretB32);
  const step = Math.floor(now / 1000 / 30);
  for (const w of [-1, 0, 1]) if (safeEqual(hotp(secret, step + w), token.trim())) return true;
  return false;
}

export function totpUri(secretB32: string, account: string, issuer = 'Maisha'): string {
  return `otpauth://totp/${encodeURIComponent(issuer)}:${encodeURIComponent(account)}?secret=${secretB32}&issuer=${encodeURIComponent(issuer)}&algorithm=SHA1&digits=6&period=30`;
}

// ---- routing / secrets ----------------------------------------------------------------

/** Routes reachable without logging in. */
export function isPublic(path: string): boolean {
  return path === '/health' || path.startsWith('/health/') || path.startsWith('/login') || path.startsWith('/docs') || path === '/metrics';
}

/** Refuse to boot in production with the shipped default secrets (P1-SECRETS). */
export function assertProductionSecrets(args: { environment: string; appPassword: string; sessionSecret: string }): void {
  if (args.environment !== 'production') return;
  const bad: string[] = [];
  if (args.appPassword === DEFAULT_PASSWORD) bad.push('MAISHA_APP_PASSWORD');
  if (args.sessionSecret === DEFAULT_SESSION_SECRET) bad.push('MAISHA_SESSION_SECRET');
  if (bad.length) {
    throw new Error(`Refusing to start in production with default secrets: ${bad.join(', ')}. Set them in the environment (see .env.example).`);
  }
}
