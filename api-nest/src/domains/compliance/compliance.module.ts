import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { ComplianceController } from './compliance.controller';
import { ComplianceCalendar } from './compliance.entities';
import { ComplianceService } from './compliance.service';

@Module({
  imports: [TypeOrmModule.forFeature([ComplianceCalendar])],
  controllers: [ComplianceController],
  providers: [ComplianceService],
})
export class ComplianceModule {}
