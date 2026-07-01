import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { Bill } from '../payables/payables.entities';
import { PayrollEntry, PayrollRun } from '../payroll/payroll.entities';
import { TaxController } from './tax.controller';
import { AdvanceTax, TdsEntry, TdsReturn } from './tax.entities';
import { TaxService } from './tax.service';

@Module({
  // Bill / PayrollRun / PayrollEntry are re-registered here so the tds-summary bridge can read
  // them; their owning modules define the schema. TypeORM allows the same entity in many features.
  imports: [TypeOrmModule.forFeature([TdsReturn, TdsEntry, AdvanceTax, PayrollRun, PayrollEntry, Bill])],
  controllers: [TaxController],
  providers: [TaxService],
})
export class TaxModule {}
