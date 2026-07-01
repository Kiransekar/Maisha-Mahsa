import { Body, Controller, Post, Res, UnauthorizedException } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsString } from 'class-validator';
import { Response } from 'express';

import { COOKIE_NAME, DEFAULT_PASSWORD, DEFAULT_SESSION_SECRET, sign, verifyPassword } from './auth';

class LoginDto {
  @IsString() password: string;
}

@ApiTags('auth')
@Controller('login')
export class AuthController {
  @Post()
  login(@Body() body: LoginDto, @Res({ passthrough: true }) res: Response) {
    const expected = process.env.MAISHA_APP_PASSWORD ?? DEFAULT_PASSWORD;
    if (!verifyPassword(body.password, expected)) {
      throw new UnauthorizedException('invalid password');
    }
    const secret = process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET;
    res.cookie(COOKIE_NAME, sign(secret), {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.MAISHA_SECURE_COOKIES === 'true',
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
import { APP_GUARD } from '@nestjs/core';
import { AuthGuard } from './auth.guard';

@Module({
  controllers: [AuthController],
  providers: [{ provide: APP_GUARD, useClass: AuthGuard }],
})
export class AuthModule {}
