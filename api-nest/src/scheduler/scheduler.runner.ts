/**
 * The long-lived scheduler (the `serve` mode of api/app/jobs.py): sleep until the next configured
 * local wall-clock time, run the daily jobs ('all'), re-arm, forever. Dependency-free (a re-armed
 * setTimeout mirrors the Python asyncio sleep loop). Off unless MAISHA_SCHEDULER_ENABLED=true.
 */
import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';

import { JobsService } from './jobs.service';
import { secondsUntilNext } from './scheduler';

@Injectable()
export class SchedulerRunner implements OnModuleInit, OnModuleDestroy {
  private readonly log = new Logger('maisha.scheduler');
  private timer?: NodeJS.Timeout;
  private stopped = false;

  constructor(private readonly jobs: JobsService) {}

  onModuleInit(): void {
    if (process.env.MAISHA_SCHEDULER_ENABLED !== 'true') return;
    const hour = Number(process.env.MAISHA_BRIEF_HOUR ?? 20);
    const minute = Number(process.env.MAISHA_BRIEF_MINUTE ?? 0);
    const tz = process.env.MAISHA_BRIEF_TZ ?? 'Asia/Kolkata';
    this.log.log(`scheduler up — daily jobs at ${hour}:${String(minute).padStart(2, '0')} ${tz}`);
    this.arm(hour, minute, tz);
  }

  onModuleDestroy(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
  }

  private arm(hour: number, minute: number, tz: string): void {
    if (this.stopped) return;
    const delayMs = Math.max(0, secondsUntilNext(new Date(), { hour, minute, tz }) * 1000);
    // ponytail: setTimeout caps at ~24.8 days; a daily delay is always well under that.
    this.timer = setTimeout(async () => {
      // Always re-arm: a throw in the tick body must not silently kill the daily loop.
      try {
        const today = new Date().toISOString().slice(0, 10);
        const result = await this.jobs.runOnce('all', today);
        this.log.log(`daily jobs ran: ${JSON.stringify(result)}`);
      } catch (e) {
        this.log.error(`daily jobs tick failed: ${(e as Error).message}`);
      } finally {
        this.arm(hour, minute, tz); // re-arm for the next day
      }
    }, delayMs);
  }
}
