/** Compliance routes (thin — delegate to the service and the loop). Mirrors router.py. */
import { Body, Controller, Get, Param, ParseIntPipe, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { MarkFiledDto, NewDeadlineDto } from './compliance.dto';
import { ComplianceService } from './compliance.service';

@ApiTags('compliance')
@Controller('api/compliance')
export class ComplianceController {
  constructor(
    private readonly service: ComplianceService,
    private readonly loop: LoopService,
  ) {}

  @Post('deadlines')
  async addDeadline(@Body() body: NewDeadlineDto) {
    return { id: await this.service.addDeadline(body) };
  }

  @Post('seed')
  async seedMonth(@Query('month') month: string) {
    return { ids: await this.service.seedMonth(month) };
  }

  @Post('deadlines/:deadline_id/file')
  async markFiled(
    @Param('deadline_id', ParseIntPipe) deadlineId: number,
    @Body() body: MarkFiledDto,
  ) {
    await this.service.markFiled(deadlineId, body);
    return { status: 'filed' };
  }

  @Get('alerts')
  alerts(@Query('as_of') asOf?: string) {
    const anchor = asOf ?? new Date().toISOString().slice(0, 10);
    return this.service.alerts(anchor);
  }

  /** Fold the compliance snapshot through Mahsa and seal it into the audit chain. */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'compliance.fold',
    });
    return {
      snapshot: outcome.snapshot,
      validation: outcome.fold.validation,
      shape: outcome.fold.shape,
      domain_intent: outcome.fold.domain_intent,
      audit_hash: outcome.auditHash,
    };
  }
}
