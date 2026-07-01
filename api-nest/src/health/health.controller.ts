import { Controller, Get } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { MahsaService } from '../mahsa/mahsa.service';

@ApiTags('health')
@Controller('health')
export class HealthController {
  constructor(private readonly mahsa: MahsaService) {}

  @Get()
  liveness() {
    return { status: 'ok', service: 'maisha-api-nest' };
  }

  /** Readiness incl. the Mahsa sidecar — degraded (not thrown) when the sidecar is down. */
  @Get('mahsa')
  async mahsaHealth() {
    try {
      return { status: 'ok', mahsa: await this.mahsa.health() };
    } catch (e) {
      return { status: 'degraded', error: (e as Error).message };
    }
  }
}

import { Module } from '@nestjs/common';
@Module({ controllers: [HealthController] })
export class HealthModule {}
