import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { TreasuryController } from './treasury.controller';
import { BankAccount, BankTransaction, FixedDeposit } from './treasury.entities';
import { TreasuryService } from './treasury.service';

@Module({
  imports: [TypeOrmModule.forFeature([BankAccount, BankTransaction, FixedDeposit])],
  controllers: [TreasuryController],
  providers: [TreasuryService],
})
export class TreasuryModule {}
