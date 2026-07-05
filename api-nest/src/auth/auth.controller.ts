import { Body, Controller, HttpException, HttpStatus, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsString } from 'class-validator';
import { Request, Response } from 'express';

import { COOKIE_NAME, DEFAULT_PASSWORD, DEFAULT_SESSION_SECRET, SESSION_TTL_MS, sign, verifyPassword } from './auth';

class LoginDto {
  @IsString() password: string;
}

// ponytail: in-process per-IP login throttle (single-instance app). Swap for a shared store only if
// the API is ever horizontally scaled.
const MAX_ATTEMPTS = 5;
const LOCKOUT_MS = 15 * 60_000;
const attempts = new Map<string, { n: number; until: number }>();

@ApiTags('auth')
@Controller('login')
export class AuthController {
  @Post()
  login(@Body() body: LoginDto, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    const ip = req.ip ?? 'unknown';
    const now = Date.now();
    const rec = attempts.get(ip);
    if (rec && rec.until > now && rec.n >= MAX_ATTEMPTS) {
      throw new HttpException('Too many login attempts. Try again later.', HttpStatus.TOO_MANY_REQUESTS);
    }

    const expected = process.env.MAISHA_APP_PASSWORD ?? DEFAULT_PASSWORD;
    if (!verifyPassword(body.password, expected)) {
      const next = rec && rec.until > now ? rec.n + 1 : 1;
      attempts.set(ip, { n: next, until: now + LOCKOUT_MS });
      throw new UnauthorizedException('invalid password');
    }
    attempts.delete(ip);

    const secret = process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET;
    res.cookie(COOKIE_NAME, sign(secret), {
      httpOnly: true,
      sameSite: 'lax',
      // Force TLS-only in production; opt-in elsewhere for local HTTPS.
      secure: process.env.MAISHA_ENVIRONMENT === 'production' || process.env.MAISHA_SECURE_COOKIES === 'true',
      maxAge: SESSION_TTL_MS,
      path: '/',
    });
    return { status: 'ok' };
  }

  @Post('logout')
  logout(@Res({ passthrough: true }) res: Response) {
    res.clearCookie(COOKIE_NAME, { path: '/' });
    return { status: 'ok' };
  }
}

import { Module } from '@nestjs/common';
import { APP_FILTER, APP_GUARD } from '@nestjs/core';
import { AuthGuard } from './auth.guard';
import { UnauthorizedRedirectFilter } from './unauthorized.filter';

@Module({
  controllers: [AuthController],
  providers: [
    { provide: APP_GUARD, useClass: AuthGuard },
    { provide: APP_FILTER, useClass: UnauthorizedRedirectFilter },
  ],
})
export class AuthModule {}
