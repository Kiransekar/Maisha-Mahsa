/** GST routes (thin — delegate to the service and the loop). Mirrors api/app/domains/gst/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { validateGstin } from './gst.calc';
import { Gstr1InputDto, Gstr3bInputDto } from './gst.dto';
import { GstService } from './gst.service';

@ApiTags('gst')
@Controller('api/gst')
export class GstController {
  constructor(
    private readonly service: GstService,
    private readonly loop: LoopService,
  ) {}

  @Get('validate-gstin')
  checkGstin(@Query('gstin') gstin: string) {
    return { valid: validateGstin(gstin) };
  }

  @Post('gstr3b')
  fileGstr3b(@Body() body: Gstr3bInputDto) {
    return this.service.fileGstr3b(body);
  }

  @Post('gstr1')
  buildGstr1(@Body() body: Gstr1InputDto) {
    return this.service.buildGstr1(body);
  }

  @Get('itc/reconcile')
  reconcile() {
    return this.service.reconcileItc();
  }

  /** Fold the GST snapshot through Mahsa and seal it into the audit chain (the Golden Rule).
   * Pass `q` to also request a verified LLM draft (when a provider is configured). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string, @Query('q') query?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      query,
      action: 'gst.fold',
    });
    return {
      snapshot: outcome.snapshot,
      validation: outcome.fold.validation,
      shape: outcome.fold.shape,
      domain_intent: outcome.fold.domain_intent,
      audit_hash: outcome.auditHash,
      claim: outcome.claim,
      claim_verified: outcome.claimVerified,
    };
  }
}
