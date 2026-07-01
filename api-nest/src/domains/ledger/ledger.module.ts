import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { LedgerController } from './ledger.controller';
import { ChartOfAccounts, FixedAsset, JournalEntry, JournalLine } from './ledger.entities';
import { LedgerService } from './ledger.service';

@Module({
  imports: [TypeOrmModule.forFeature([ChartOfAccounts, JournalEntry, JournalLine, FixedAsset])],
  controllers: [LedgerController],
  providers: [LedgerService],
})
export class LedgerModule {}
