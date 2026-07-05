/** The server-rendered web UI (premium "Metallic Black" dashboard). */
import { Module } from '@nestjs/common';

import { SchedulerModule } from '../scheduler/scheduler.module';
import { TaxOptimizerModule } from '../tax-optimizer/tax-optimizer.module';
import { WebController } from './web.controller';

@Module({
  imports: [SchedulerModule, TaxOptimizerModule], // DomainRegistry + TaxOptimizer (Mahsa/Audit/Memory are global)
  controllers: [WebController],
})
export class WebModule {}
