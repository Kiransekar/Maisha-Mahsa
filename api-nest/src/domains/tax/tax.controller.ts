/** Tax routes (thin — delegate to the service and the loop). Mirrors api/app/domains/tax/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { interest234c } from './tax.calc';
import { Interest234cInputDto, TdsReturnInputDto } from './tax.dto';
import { TaxService } from './tax.service';

@ApiTags('tax')
@Controller('api/tax')
export class TaxController {
  constructor(
    private readonly service: TaxService,
    private readonly loop: LoopService,
  ) {}

  @Post('tds-returns')
  fileTdsReturn(@Body() body: TdsReturnInputDto) {
    return this.service.fileTdsReturn(body);
  }

  @Get('tds-summary')
  tdsSummary(@Query('month') month: string) {
    return this.service.tdsDeductedSummary(month);
  }

  @Post('advance-tax/234c')
  compute234c(@Body() body: Interest234cInputDto) {
    return interest234c(body.total_liability, body.cumulative_paid);
  }

  /** Fold the tax snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'tax.fold',
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
