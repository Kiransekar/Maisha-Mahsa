import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { EquityController } from './equity.controller';
import { CapTableSnapshot, SafeNote, Shareholder } from './equity.entities';
import { EquityService } from './equity.service';

@Module({
  imports: [TypeOrmModule.forFeature([Shareholder, SafeNote, CapTableSnapshot])],
  controllers: [EquityController],
  providers: [EquityService],
})
export class EquityModule {}
