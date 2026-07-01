/**
 * Forecast service: budget variance, rolling cash projection, scenarios, unit economics,
 * and the forecast health snapshot for Mahsa. Deterministic; money in paise.
 * Mirrors api/app/domains/forecast/service.py.
 *
 * Forecast has no Mahsa sub-vector; Mahsa enforces FORECAST-001 (projected cash must not go
 * negative) on the snapshot's forecast_min_cash.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as forecastCalc from './forecast.calc';
import { RecordForecastDto, ScenarioInputDto, UnitEconomicsInputDto } from './forecast.dto';
import { Forecast } from './forecast.entities';

@Injectable()
export class ForecastService implements SnapshotProducer {
  readonly domain = 'forecast';

  constructor(@InjectRepository(Forecast) private readonly forecasts: Repository<Forecast>) {}

  // ---- projections --------------------------------------------------------------

  projectCash(openingCash: number, monthlyNetChange: number[]) {
    return forecastCalc.projectCash(openingCash, monthlyNetChange);
  }

  scenario(body: ScenarioInputDto) {
    const net = forecastCalc.scenarioNetChange(body.base_revenue, body.base_cost, {
      revenue_mult: body.revenue_mult,
      extra_cost: body.extra_cost,
    });
    const horizon = body.horizon_months ?? 12;
    const projection = forecastCalc.projectCash(body.opening_cash, new Array<number>(horizon).fill(net));
    return { monthly_net_change: net, ...projection };
  }

  unitEconomics(body: UnitEconomicsInputDto) {
    return forecastCalc.unitEconomics(body);
  }

  revenueRecognitionForecast(
    contracts: forecastCalc.RevContract[],
    opts: { horizon_months: number; start: string },
  ) {
    return forecastCalc.revenueRecognitionForecast(contracts, opts);
  }

  // ---- persistence --------------------------------------------------------------

  async recordForecast(body: RecordForecastDto) {
    const projection = forecastCalc.projectCash(body.opening_cash, body.monthly_net_change);
    const row = this.forecasts.create({
      forecast_date: body.forecast_date,
      horizon_months: body.horizon_months ?? 12,
      scenario: body.scenario ?? 'base',
      cash_forecast: projection.min_cash,
      runway_forecast: projection.months_to_zero,
    });
    await this.forecasts.save(row);
    return { forecast_id: row.id, ...projection };
  }

  // ---- Mahsa contract -----------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchorIso = asOf ?? '1970-01-01';
    const latest = await this.forecasts.findOne({ where: {}, order: { id: 'DESC' } });
    const minCash =
      latest && latest.cash_forecast !== null && latest.cash_forecast !== undefined
        ? Math.trunc(latest.cash_forecast)
        : 0;
    const runway = latest ? latest.runway_forecast : null;
    return {
      as_of: anchorIso,
      metrics: {
        // consumed by FORECAST-001 (must be >= 0)
        forecast_min_cash_paise: minCash,
        forecast_runway_months: runway !== null && runway !== undefined ? runway : 999,
      },
    };
  }
}
