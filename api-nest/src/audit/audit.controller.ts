import { Controller, Get } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { AuditService } from './audit.service';

@ApiTags('audit')
@Controller('api/audit')
export class AuditController {
  constructor(private readonly audit: AuditService) {}

  /** Verify the hash chain is intact (tamper-evidence check). */
  @Get('verify')
  async verify() {
    return { intact: await this.audit.verify() };
  }

  @Get('chain')
  async chain() {
    return this.audit.loadChain();
  }
}
