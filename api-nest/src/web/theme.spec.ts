import { formatMetric, humanize, sparkline } from './theme';

const inr = (paise: number) => `₹${(paise / 100).toFixed(2)}`;

describe('formatMetric — legible figures, never a bare normalised score', () => {
  it('formats paise keys as rupees', () => {
    expect(formatMetric('closing_balance_paise', 123456, inr).value).toBe('₹1234.56');
    expect(formatMetric('available_2b_paise', 0, inr).value).toBe('₹0.00');
  });
  it('formats rupee, month, count and day units', () => {
    expect(formatMetric('annual_turnover_rupees', 100, inr).value).toBe('₹100.00');
    expect(formatMetric('forecast_runway_months', 7.25, inr)).toEqual({ value: '7.3', note: 'months' });
    expect(formatMetric('gstr3b_days_late', 16, inr)).toEqual({ value: '16', note: 'days' });
    expect(formatMetric('bank_account_count', 3, inr).value).toBe('3');
  });
  it('turns 0..1 scores and ratios into percentages', () => {
    expect(formatMetric('filing_timeliness', 0, inr).value).toBe('0%');
    expect(formatMetric('itc_claimed_ratio', 1, inr).value).toBe('100%');
    expect(formatMetric('hsn_accuracy', 0.5, inr).value).toBe('50%');
  });
  it('leaves a plain out-of-range number as-is (no fake percent)', () => {
    expect(formatMetric('some_index', 4.2, inr).value).toBe('4.2');
  });
});

describe('humanize', () => {
  it('uppercases acronyms and strips unit suffixes', () => {
    expect(humanize('gstr3b_days_late')).toBe('GSTR-3B Days Late');
    expect(humanize('itc_claimed_ratio')).toBe('ITC Claimed');
    expect(humanize('esop_pool_pct')).toBe('ESOP Pool');
  });
});

describe('sparkline — honest about missing history', () => {
  it('renders nothing plottable below two real points', () => {
    expect(sparkline([])).toContain('not enough history');
    expect(sparkline([5])).toContain('not enough history');
  });
  it('draws a path for two or more points', () => {
    const svg = sparkline([1, 2, 3]);
    expect(svg).toContain('<path');
    expect(svg).toMatch(/M0/);
  });
});
