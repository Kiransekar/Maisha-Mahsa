/** The server-rendered web UI (premium "Metallic Black" dashboard). */
import { Module } from '@nestjs/common';

import { SchedulerModule } from '../scheduler/scheduler.module';
import { WebController } from './web.controller';

@Module({
  imports: [SchedulerModule], // for DomainRegistry (Mahsa/Audit/Loop come from the global CoreModule)
  controllers: [WebController],
})
export class WebModule {}
