import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { ForecastController } from './forecast.controller';
import { Budget, Forecast } from './forecast.entities';
import { ForecastService } from './forecast.service';

@Module({
  imports: [TypeOrmModule.forFeature([Budget, Forecast])],
  controllers: [ForecastController],
  providers: [ForecastService],
})
export class ForecastModule {}
