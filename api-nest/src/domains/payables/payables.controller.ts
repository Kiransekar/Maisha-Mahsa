/** Payables routes (thin — delegate to the service and the loop). Mirrors api/app/domains/payables/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { NewBillDto, NewVendorDto } from './payables.dto';
import { PayablesService } from './payables.service';

@ApiTags('payables')
@Controller('api/payables')
export class PayablesController {
  constructor(
    private readonly service: PayablesService,
    private readonly loop: LoopService,
  ) {}

  @Post('vendors')
  createVendor(@Body() body: NewVendorDto) {
    return this.service.createVendor(body);
  }

  @Post('bills')
  createBill(@Body() body: NewBillDto) {
    return this.service.createBill(body);
  }

  @Get('ap-aging')
  apAging(@Query('as_of') asOf?: string) {
    const anchor = asOf ?? new Date().toISOString().slice(0, 10);
    return this.service.apAging(anchor);
  }

  @Get('itc')
  itc(@Query('period') period: string) {
    return this.service.inputTaxCredit(period);
  }

  /** Fold the payables snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'payables.fold',
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
