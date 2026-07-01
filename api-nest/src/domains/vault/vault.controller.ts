/** Vault routes (thin — delegate to the service and the loop). Mirrors api/app/domains/vault/router.py. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { IngestDocumentDto } from './vault.dto';
import { VaultService } from './vault.service';

@ApiTags('vault')
@Controller('api/vault')
export class VaultController {
  constructor(
    private readonly service: VaultService,
    private readonly loop: LoopService,
  ) {}

  @Post('documents')
  ingest(@Body() body: IngestDocumentDto) {
    const upload_date = new Date().toISOString().slice(0, 10);
    return this.service.ingest({ ...body, upload_date });
  }

  @Get('search')
  search(@Query('q') q: string) {
    return this.service.search(q);
  }

  /** Fold the vault snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'vault.fold',
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
