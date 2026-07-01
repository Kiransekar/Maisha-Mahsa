/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/forecast/forecast_calc.py). If the TS port drifts, this fails.
 */
import * as f from './forecast.calc';

describe('forecast.calc — parity with Python reference', () => {
  it('revenue recognition (straight-line, remainder trued into last month)', () => {
    const r = f.revenueRecognitionForecast(
      [
        { total_paise: 1000000, start: '2024-01', term_months: 3 },
        { total_paise: 1000, start: '2024-02', term_months: 3 },
      ],
      { horizon_months: 6, start: '2024-01' },
    );
    expect(r).toEqual({
      start: '2024-01',
      horizon_months: 6,
      monthly: [333333, 333666, 333667, 334, 0, 0],
      total_recognized: 1001000,
    });
  });

  it('variance (over / under / zero budget)', () => {
    expect(f.variance(120000, 100000)).toEqual({ amount: 20000, pct: 20.0, over_budget: true });
    expect(f.variance(80000, 100000)).toEqual({ amount: -20000, pct: -20.0, over_budget: false });
    expect(f.variance(500, 0)).toEqual({ amount: 500, pct: 0.0, over_budget: true });
  });

  it('project cash (overdraft detection + empty horizon)', () => {
    expect(f.projectCash(1000000, [-300000, -300000, -500000, 200000])).toEqual({
      balances: [700000, 400000, -100000, 100000],
      min_cash: -100000,
      months_to_zero: 2,
    });
    expect(f.projectCash(1000000, [])).toEqual({
      balances: [],
      min_cash: 1000000,
      months_to_zero: null,
    });
  });

  it('scenario net change (exact Decimal multiply, truncate toward zero)', () => {
    expect(f.scenarioNetChange(500000, 400000, { revenue_mult: 1.5, extra_cost: 50000 })).toBe(300000);
    expect(f.scenarioNetChange(500000, 400000)).toBe(100000);
  });

  it('runway + burn multiple (None when not applicable)', () => {
    expect(f.runwayMonths(1000000, 150000)).toBe(6.67);
    expect(f.runwayMonths(1000000, 0)).toBeNull();
    expect(f.burnMultiple(1000000, 400000)).toBe(2.5);
    expect(f.burnMultiple(1000000, 0)).toBeNull();
  });

  it('unit economics (CAC / LTV / payback / LTV:CAC)', () => {
    expect(
      f.unitEconomics({
        sales_marketing_spend: 1000000,
        new_customers: 10,
        arpu: 50000,
        gross_margin: 0.8,
        lifetime_months: 24,
      }),
    ).toEqual({ cac: 100000, ltv: 960000, payback_months: 2.5, ltv_cac_ratio: 9.6 });
    expect(() =>
      f.unitEconomics({
        sales_marketing_spend: 1,
        new_customers: 0,
        arpu: 1,
        gross_margin: 0.5,
        lifetime_months: 1,
      }),
    ).toThrow('new_customers must be positive');
  });

  it('rolling re-forecast (blend actuals over budget)', () => {
    expect(f.rollingReforecast([100, 200, 300], [100, 100, 100, 100, 100])).toEqual({
      reforecast: [100, 200, 300, 100, 100],
      reforecast_total: 800,
      original_total: 500,
      variance: 300,
      periods_actualised: 3,
    });
  });

  it('headcount forecast (loaded monthly + annualised + flat projection)', () => {
    expect(
      f.headcountForecast(
        [
          { count: 3, monthly_cost: 5000000 },
          { count: 2, monthly_cost: 8000000 },
        ],
        { months: 4 },
      ),
    ).toEqual({
      headcount: 5,
      monthly_cost: 31000000,
      annualised_cost: 372000000,
      projection: [31000000, 31000000, 31000000, 31000000],
    });
  });
});
