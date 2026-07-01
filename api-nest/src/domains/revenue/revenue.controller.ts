/** Revenue routes (thin — delegate to the service and the loop). Mirrors api/app/domains/revenue/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { NewCustomerDto, NewInvoiceDto } from './revenue.dto';
import { RevenueService } from './revenue.service';

/** ISO date default anchor when `as_of` is omitted (UTC today). */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

@ApiTags('revenue')
@Controller('api/revenue')
export class RevenueController {
  constructor(
    private readonly service: RevenueService,
    private readonly loop: LoopService,
  ) {}

  @Post('customers')
  createCustomer(@Body() body: NewCustomerDto) {
    return this.service.createCustomer(body);
  }

  @Post('invoices')
  createInvoice(@Body() body: NewInvoiceDto) {
    return this.service.createInvoice(body);
  }

  @Get('ar-aging')
  arAging(@Query('as_of') asOf?: string) {
    return this.service.arAging(asOf ?? todayIso());
  }

  @Get('dunning')
  dunning(@Query('as_of') asOf?: string) {
    return this.service.dueDunning(asOf ?? todayIso());
  }

  /** Fold the revenue snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'revenue.fold',
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
