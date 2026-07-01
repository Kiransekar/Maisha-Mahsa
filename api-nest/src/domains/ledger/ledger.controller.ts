/** Ledger routes (thin — delegate to the service and the loop). Mirrors api/app/domains/ledger/router.py. */
import { BadRequestException, Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { NewAccountDto, NewJournalEntryDto } from './ledger.dto';
import { LedgerService } from './ledger.service';

@ApiTags('ledger')
@Controller('api/ledger')
export class LedgerController {
  constructor(
    private readonly service: LedgerService,
    private readonly loop: LoopService,
  ) {}

  @Post('accounts')
  async createAccount(@Body() body: NewAccountDto) {
    try {
      const id = await this.service.createAccount(body);
      return { id };
    } catch (exc) {
      throw new BadRequestException((exc as Error).message);
    }
  }

  @Post('journal')
  async postJournal(@Body() body: NewJournalEntryDto) {
    try {
      return await this.service.postJournalEntry({
        entry_date: body.entry_date,
        description: body.description,
        lines: body.lines,
        source: body.source,
        reference: body.reference,
      });
    } catch (exc) {
      throw new BadRequestException((exc as Error).message);
    }
  }

  @Get('trial-balance')
  trialBalance() {
    return this.service.trialBalance();
  }

  @Get('pnl')
  pnl() {
    return this.service.profitAndLoss();
  }

  @Get('balance-sheet')
  balanceSheet() {
    return this.service.balanceSheet();
  }

  /** Fold the ledger snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'ledger.fold',
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
