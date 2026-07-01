/** Global login guard: every route needs a valid signed cookie except the public allowlist. */
import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { Request } from 'express';

import { COOKIE_NAME, DEFAULT_SESSION_SECRET, isPublic, validCookie } from './auth';

@Injectable()
export class AuthGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();
    if (isPublic(req.path)) return true;

    const secret = process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET;
    const cookie = parseCookie(req.headers.cookie, COOKIE_NAME);
    if (validCookie(cookie, secret)) return true;
    throw new UnauthorizedException('login required');
  }
}

// ponytail: one-line cookie parse — no cookie-parser dep for a single cookie lookup.
function parseCookie(header: string | undefined, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(';')) {
    const [k, ...v] = part.trim().split('=');
    if (k === name) return decodeURIComponent(v.join('='));
  }
  return null;
}
