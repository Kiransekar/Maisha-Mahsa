/** Forecast routes (thin — delegate to the service and the loop). Mirrors api/app/domains/forecast/router.py. */
import { Body, Controller, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import {
  CashProjectionInputDto,
  RecordForecastDto,
  ScenarioInputDto,
  UnitEconomicsInputDto,
} from './forecast.dto';
import { ForecastService } from './forecast.service';

@ApiTags('forecast')
@Controller('api/forecast')
export class ForecastController {
  constructor(
    private readonly service: ForecastService,
    private readonly loop: LoopService,
  ) {}

  @Post('project')
  project(@Body() body: CashProjectionInputDto) {
    return this.service.projectCash(body.opening_cash, body.monthly_net_change);
  }

  @Post('scenario')
  scenario(@Body() body: ScenarioInputDto) {
    return this.service.scenario(body);
  }

  @Post('unit-economics')
  unitEconomics(@Body() body: UnitEconomicsInputDto) {
    return this.service.unitEconomics(body);
  }

  @Post('forecasts')
  recordForecast(@Body() body: RecordForecastDto) {
    return this.service.recordForecast(body);
  }

  /** Fold the forecast snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'forecast.fold',
    });
    return {
      snapshot: outcome.snapshot,
      validation: outcome.fold.validation,
      shape: outcome.fold.shape,
      domain_intent: outcome.fold.domain_intent,
      audit_hash: outcome.auditHash,
    };
  }
}
