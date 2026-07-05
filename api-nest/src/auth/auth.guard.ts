/**
 * Global auth + RBAC guard. Verifies the signed session cookie, sets the request user (for audit),
 * and enforces roles: an explicit @Roles wins; otherwise the method-based default — writes
 * (POST/PUT/PATCH/DELETE) require a writer role (admin/operator); reads (GET) allow any authenticated
 * user. Viewers are therefore read-only everywhere without decorating every route.
 */
import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Request } from 'express';

import { COOKIE_NAME, DEFAULT_SESSION_SECRET, isPublic, Role, verifySession, WRITER_ROLES } from './auth';
import { setRequestUser } from './request-context';
import { ROLES_KEY } from './roles.decorator';

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();
    if (isPublic(req.path)) return true;

    const secret = process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET;
    const claims = verifySession(parseCookie(req.headers.cookie, COOKIE_NAME), secret);
    if (!claims) throw new UnauthorizedException('login required');
    setRequestUser({ sub: claims.sub, role: claims.role });

    const required = this.reflector.getAllAndOverride<Role[] | undefined>(ROLES_KEY, [context.getHandler(), context.getClass()]);
    if (required && required.length) {
      if (!required.includes(claims.role)) throw new ForbiddenException(`requires role: ${required.join(' or ')}`);
      return true;
    }
    // Default policy: writes need a writer role; reads are open to any authenticated user.
    if (WRITE_METHODS.has(req.method) && !WRITER_ROLES.includes(claims.role)) {
      throw new ForbiddenException('read-only role cannot perform this action');
    }
    return true;
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
