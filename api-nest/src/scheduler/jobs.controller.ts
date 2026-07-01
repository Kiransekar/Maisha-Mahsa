/** Trigger scheduled jobs on demand (the CLI equivalent of `python -m app.jobs <command>`). */
import { BadRequestException, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { JobCommand, JobsService } from './jobs.service';
import { HistoryService } from './history.service';

const COMMANDS = new Set<JobCommand>(['capture', 'brief', 'dunning', 'alerts', 'audit-verify', 'all']);

@ApiTags('jobs')
@Controller('api/jobs')
export class JobsController {
  constructor(
    private readonly jobs: JobsService,
    private readonly history: HistoryService,
  ) {}

  /** Run one job now. `as_of` defaults to today (UTC). */
  @Post(':command')
  run(@Param('command') command: string, @Query('as_of') asOf?: string) {
    if (!COMMANDS.has(command as JobCommand)) {
      throw new BadRequestException(`unknown job '${command}'; one of ${[...COMMANDS].join(', ')}`);
    }
    return this.jobs.runOnce(command as JobCommand, asOf ?? new Date().toISOString().slice(0, 10));
  }

  /** Captured metric trend series for a domain (for charts). */
  @Get('history/:domain')
  history_series(@Param('domain') domain: string) {
    return this.history.domainSeries(domain);
  }
}
