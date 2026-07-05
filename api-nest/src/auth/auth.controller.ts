import { Body, Controller, Get, HttpException, HttpStatus, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsOptional, IsString } from 'class-validator';
import { Request, Response } from 'express';

import { COOKIE_NAME, DEFAULT_PASSWORD, DEFAULT_SESSION_SECRET, Role, SESSION_TTL_MS, signSession, verifyPassword, verifySession } from './auth';
import { UsersService } from './users.service';

class LoginDto {
  @IsOptional() @IsString() email?: string;
  @IsString() password: string;
  @IsOptional() @IsString() totp?: string;
}

// ponytail: in-process per-IP login throttle (single-instance). Swap for a shared store (Redis) when
// horizontally scaled — see the HA hardening tranche.
const MAX_ATTEMPTS = 5;
const LOCKOUT_MS = 15 * 60_000;
const attempts = new Map<string, { n: number; until: number }>();

@ApiTags('auth')
@Controller('login')
export class AuthController {
  constructor(private readonly users: UsersService) {}

  @Post()
  async login(@Body() body: LoginDto, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    const ip = req.ip ?? 'unknown';
    const now = Date.now();
    const rec = attempts.get(ip);
    if (rec && rec.until > now && rec.n >= MAX_ATTEMPTS) {
      throw new HttpException('Too many login attempts. Try again later.', HttpStatus.TOO_MANY_REQUESTS);
    }

    let sub: string;
    let role: Role;
    try {
      if (body.email) {
        const u = await this.users.verifyLogin(body.email, body.password, body.totp);
        sub = u.id;
        role = u.role;
      } else {
        // Break-glass bootstrap: password-only against MAISHA_APP_PASSWORD → admin.
        if (!verifyPassword(body.password, process.env.MAISHA_APP_PASSWORD ?? DEFAULT_PASSWORD)) throw new UnauthorizedException('invalid credentials');
        sub = 'bootstrap';
        role = 'admin';
      }
    } catch (e) {
      const next = rec && rec.until > now ? rec.n + 1 : 1;
      attempts.set(ip, { n: next, until: now + LOCKOUT_MS });
      throw e instanceof HttpException ? e : new UnauthorizedException('invalid credentials');
    }
    attempts.delete(ip);

    const secret = process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET;
    res.cookie(COOKIE_NAME, signSession(secret, { sub, role }), {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.MAISHA_ENVIRONMENT === 'production' || process.env.MAISHA_SECURE_COOKIES === 'true',
      maxAge: SESSION_TTL_MS,
      path: '/',
    });
    return { status: 'ok', role };
  }

  @Post('logout')
  logout(@Res({ passthrough: true }) res: Response) {
    res.clearCookie(COOKIE_NAME, { path: '/' });
    return { status: 'ok' };
  }

  /** The current session's identity (for the UI to show role / gate controls). Public path, so it
   *  verifies the cookie itself rather than relying on the guard's request context. */
  @Get('me')
  me(@Req() req: Request) {
    const raw = (req.headers.cookie ?? '').split(';').map((s) => s.trim()).find((s) => s.startsWith(`${COOKIE_NAME}=`));
    const token = raw ? decodeURIComponent(raw.slice(COOKIE_NAME.length + 1)) : null;
    const claims = verifySession(token, process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET);
    return { sub: claims?.sub ?? null, role: claims?.role ?? null };
  }
}

import { Module } from '@nestjs/common';
import { APP_FILTER, APP_GUARD } from '@nestjs/core';
import { TypeOrmModule } from '@nestjs/typeorm';
import { User } from '../common/shared.entities';
import { AuthGuard } from './auth.guard';
import { UnauthorizedRedirectFilter } from './unauthorized.filter';
import { UsersController } from './users.controller';

@Module({
  imports: [TypeOrmModule.forFeature([User])],
  controllers: [AuthController, UsersController],
  providers: [
    UsersService,
    { provide: APP_GUARD, useClass: AuthGuard },
    { provide: APP_FILTER, useClass: UnauthorizedRedirectFilter },
  ],
  exports: [UsersService],
})
export class AuthModule {}
