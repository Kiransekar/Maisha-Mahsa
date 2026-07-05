/** Tax Optimizer (procedural memory + deterministic headroom). */
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { Company } from '../common/shared.entities';
import { SchedulerModule } from '../scheduler/scheduler.module';
import { TaxOptimizerController } from './tax-optimizer.controller';
import { TaxOptimizerService } from './tax-optimizer.service';

@Module({
  imports: [SchedulerModule, TypeOrmModule.forFeature([Company])], // DomainRegistry from SchedulerModule; Mahsa/Audit/Memory are global
  controllers: [TaxOptimizerController],
  providers: [TaxOptimizerService],
  exports: [TaxOptimizerService],
})
export class TaxOptimizerModule {}
