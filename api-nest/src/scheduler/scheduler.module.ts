/** Scheduler + email track: history capture, CFO brief, statutory alerts, dunning, audit-verify. */
import { Module } from '@nestjs/common';
import { DiscoveryModule } from '@nestjs/core';
import { TypeOrmModule } from '@nestjs/typeorm';

import { MetricSnapshot } from '../common/shared.entities';
import { EmailChannel } from '../email/channel';
import { buildTransport } from '../email/transport';
import { DomainRegistry } from './registry.service';
import { HistoryService } from './history.service';
import { JobsService } from './jobs.service';
import { JobsController } from './jobs.controller';
import { SchedulerRunner } from './scheduler.runner';

@Module({
  imports: [DiscoveryModule, TypeOrmModule.forFeature([MetricSnapshot])],
  controllers: [JobsController],
  providers: [
    DomainRegistry,
    HistoryService,
    JobsService,
    SchedulerRunner,
    // Email channel over the env-selected transport (InMemory unless MAISHA_SMTP_ENABLED=true).
    {
      provide: EmailChannel,
      useFactory: () => new EmailChannel(buildTransport(), process.env.MAISHA_EMAIL_SENDER ?? 'cfo@maisha-mahsa.local'),
    },
  ],
  exports: [DomainRegistry, HistoryService],
})
export class SchedulerModule {}
