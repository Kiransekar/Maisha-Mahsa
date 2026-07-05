import { Controller, Get, HttpException, HttpStatus } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { ApiTags } from '@nestjs/swagger';
import { DataSource } from 'typeorm';

import { MahsaService } from '../mahsa/mahsa.service';

@ApiTags('health')
@Controller('health')
export class HealthController {
  constructor(
    private readonly mahsa: MahsaService,
    @InjectDataSource() private readonly ds: DataSource,
  ) {}

  /** Liveness: the process is up. Cheap; never touches dependencies (for k8s livenessProbe). */
  @Get()
  liveness() {
    return { status: 'ok', service: 'maisha-api-nest' };
  }

  @Get('live')
  live() {
    return { status: 'ok' };
  }

  /** Readiness: DB reachable (hard) + Mahsa reachable (soft). 503 if the DB is down so k8s stops
   *  routing traffic to a broken instance (readinessProbe). */
  @Get('ready')
  async ready() {
    let db = 'ok';
    try {
      await this.ds.query('SELECT 1');
    } catch (e) {
      db = 'down';
    }
    let mahsa = 'ok';
    try {
      await this.mahsa.health();
    } catch {
      mahsa = 'down';
    }
    const body = { status: db === 'ok' ? 'ready' : 'not-ready', db, mahsa };
    if (db !== 'ok') throw new HttpException(body, HttpStatus.SERVICE_UNAVAILABLE);
    return body;
  }

  /** Mahsa sidecar detail — degraded (not thrown) when the sidecar is down. */
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
