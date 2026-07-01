/**
 * Faithfulness check: every expected value here was produced by the Python reference
 * (api/app/domains/equity/equity_calc.py). If the TS port drifts, this fails.
 */
import * as e from './equity.calc';

describe('equity.calc — parity with Python reference', () => {
  it('ownership aggregation + pct', () => {
    expect(
      e.ownership([
        { category: 'founder', shares: 600000 },
        { category: 'founder', shares: 300000 },
        { category: 'investor', shares: 80000 },
        { category: 'esop', shares: 20000 },
      ]),
    ).toEqual({
      total_shares: 1000000,
      by_category: { founder: 900000, investor: 80000, esop: 20000 },
      pct: { founder: 0.9, investor: 0.08, esop: 0.02 },
    });
    expect(e.ownership([])).toEqual({ total_shares: 0, by_category: {}, pct: {} });
  });

  it('esop pool pct', () => {
    expect(e.esopPoolPct(20000, 1000000)).toBe(0.02);
    expect(e.esopPoolPct(20000, 0)).toBe(0.0);
  });

  it('SAFE conversion — cap vs discount (better-for-investor wins)', () => {
    expect(
      e.safeConversion({
        investment: 5000000,
        valuation_cap: 100000000,
        discount_rate: 0.2,
        round_price_per_share: 200,
        pre_round_shares: 1000000,
      }),
    ).toEqual({ conversion_price_paise: 100, shares_issued: 50000 });
    expect(
      e.safeConversion({
        investment: 5000000,
        valuation_cap: null,
        discount_rate: 0.2,
        round_price_per_share: 200,
        pre_round_shares: 1000000,
      }),
    ).toEqual({ conversion_price_paise: 160, shares_issued: 31250 });
    expect(
      e.safeConversion({
        investment: 5000000,
        valuation_cap: null,
        discount_rate: 0.0,
        round_price_per_share: 200,
        pre_round_shares: 1000000,
      }),
    ).toEqual({ conversion_price_paise: 200, shares_issued: 25000 });
  });

  it('post-round ownership', () => {
    expect(e.postRoundOwnership(300000, 1000000, 50000)).toBe(0.285714);
  });

  it('convertible note — simple & monthly compounding', () => {
    expect(e.convertibleNoteValue(10000000, { annual_rate: 0.08, months: 18, compounding: 'simple' })).toEqual({
      principal: 10000000,
      interest: 1200000,
      maturity_value: 11200000,
    });
    expect(e.convertibleNoteValue(10000000, { annual_rate: 0.08, months: 18, compounding: 'monthly' })).toEqual({
      principal: 10000000,
      interest: 1270479,
      maturity_value: 11270479,
    });
  });

  it('share certificates — contiguous distinctive numbers, skip zero holdings', () => {
    expect(
      e.shareCertificates([
        { name: 'Alice', shares: 600000 },
        { name: 'Bob', shares: 0 },
        { name: 'Carol', shares: 300000, form: 'physical' },
      ]),
    ).toEqual([
      { certificate_no: 'SC-0001', name: 'Alice', shares: 600000, distinctive_from: 1, distinctive_to: 600000, form: 'demat' },
      { certificate_no: 'SC-0002', name: 'Carol', shares: 300000, distinctive_from: 600001, distinctive_to: 900000, form: 'physical' },
    ]);
  });

  it('rights entitlement — pro rata', () => {
    expect(
      e.rightsEntitlement(
        [
          { name: 'Alice', shares: 600000 },
          { name: 'Bob', shares: 300000 },
          { name: 'Carol', shares: 100000 },
        ],
        100000,
      ),
    ).toEqual([
      { name: 'Alice', shares: 600000, entitlement: 60000 },
      { name: 'Bob', shares: 300000, entitlement: 30000 },
      { name: 'Carol', shares: 100000, entitlement: 10000 },
    ]);
  });

  it('buyback compliance — s.68 limits', () => {
    expect(
      e.buybackCompliance({
        paid_up_capital: 100000000,
        free_reserves: 100000000,
        buyback_amount: 40000000,
        shares_bought_back: 100000,
        total_shares: 1000000,
        post_buyback_debt: 100000000,
        post_buyback_equity: 100000000,
      }),
    ).toEqual({ permitted: true, max_amount: 50000000, debt_equity_ratio: 1.0, reasons: [] });
    expect(
      e.buybackCompliance({
        paid_up_capital: 100000000,
        free_reserves: 0,
        buyback_amount: 40000000,
        shares_bought_back: 300000,
        total_shares: 1000000,
        post_buyback_debt: 300000000,
        post_buyback_equity: 100000000,
      }),
    ).toEqual({
      permitted: false,
      max_amount: 25000000,
      debt_equity_ratio: 3.0,
      reasons: [
        'buyback exceeds 25% of paid-up capital + free reserves',
        'shares bought back exceed 25% of total equity',
        'post-buyback debt:equity exceeds 2:1',
      ],
    });
  });

  it('dividend distribution — s.123 out-of-profits check', () => {
    expect(e.dividendDistribution({ distributable_profit: 100000000, declared: 50000000, shares: 1000000 })).toEqual({
      permitted: true,
      declared: 50000000,
      per_share: 50,
      remaining_profit: 50000000,
    });
    expect(e.dividendDistribution({ distributable_profit: 100000000, declared: 200000000, shares: 1000000 })).toEqual({
      permitted: false,
      declared: 0,
      per_share: 0,
      remaining_profit: 100000000,
    });
  });
});
