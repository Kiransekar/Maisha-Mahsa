/** Treasury routes (thin — delegate to the service and the loop). Mirrors api/app/domains/treasury/router.py. */
import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  ParseIntPipe,
  Post,
  Query,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { ImportCsvDto, NewAccountDto } from './treasury.dto';
import { TreasuryService } from './treasury.service';

@ApiTags('treasury')
@Controller('api/treasury')
export class TreasuryController {
  constructor(
    private readonly service: TreasuryService,
    private readonly loop: LoopService,
  ) {}

  @Post('accounts')
  createAccount(@Body() body: NewAccountDto) {
    return this.service.createAccount(body);
  }

  // Accepts either a CSV text body (JSON) or a multipart `file` upload (bank statement export).
  @Post('accounts/:account_id/import')
  async importStatement(
    @Param('account_id', ParseIntPipe) accountId: number,
    @Body() body: ImportCsvDto,
  ) {
    try {
      return await this.service.importCsv(accountId, body.csv_text);
    } catch (exc) {
      throw new BadRequestException((exc as Error).message);
    }
  }

  /** Import a bank statement CSV as a multipart `file` upload (utf-8, BOM tolerated). */
  @Post('accounts/:account_id/import/file')
  @UseInterceptors(FileInterceptor('file'))
  async importStatementFile(
    @Param('account_id', ParseIntPipe) accountId: number,
    @UploadedFile() file: Express.Multer.File,
  ) {
    if (!file) throw new BadRequestException('multipart field `file` (a CSV) is required');
    const text = file.buffer.toString('utf-8').replace(/^﻿/, ''); // strip UTF-8 BOM (utf-8-sig)
    try {
      return await this.service.importCsv(accountId, text);
    } catch (exc) {
      throw new BadRequestException((exc as Error).message);
    }
  }

  @Get('cash')
  cash() {
    return this.service.cashPosition();
  }

  @Get('metrics')
  metrics(@Query('as_of') asOf?: string) {
    const anchor = asOf ?? new Date().toISOString().slice(0, 10);
    return this.service.metrics(anchor);
  }

  /** Fold the treasury snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'treasury.fold',
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
