import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { GstController } from './gst.controller';
import { GstReturn, ItcRegister } from './gst.entities';
import { GstService } from './gst.service';

@Module({
  imports: [TypeOrmModule.forFeature([GstReturn, ItcRegister])],
  controllers: [GstController],
  providers: [GstService],
})
export class GstModule {}
