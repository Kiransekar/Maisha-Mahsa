/** Equity routes (thin — delegate to the service and the loop). Mirrors api/app/domains/equity/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { NewShareholderDto, SafeConversionInputDto } from './equity.dto';
import { EquityService } from './equity.service';

@ApiTags('equity')
@Controller('api/equity')
export class EquityController {
  constructor(
    private readonly service: EquityService,
    private readonly loop: LoopService,
  ) {}

  @Post('shareholders')
  async addShareholder(@Body() body: NewShareholderDto) {
    return { id: await this.service.addShareholder(body) };
  }

  @Get('cap-table')
  capTable() {
    return this.service.capTable();
  }

  @Post('safe/convert')
  convertSafe(@Body() body: SafeConversionInputDto) {
    return this.service.convertSafe(body);
  }

  @Post('snapshot')
  async snapshot(
    @Query('snapshot_date') snapshotDate: string,
    @Query('esop_board_approved') esopBoardApproved?: string,
  ) {
    const approved = esopBoardApproved === undefined ? true : esopBoardApproved !== 'false';
    return { id: await this.service.snapshotCapTable(snapshotDate, approved) };
  }

  /** Fold the equity snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'equity.fold',
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
