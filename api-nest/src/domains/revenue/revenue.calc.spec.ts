/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/revenue/revenue_calc.py). If the TS port drifts, this fails.
 */
import * as r from './revenue.calc';

describe('revenue.calc — parity with Python reference', () => {
  it('compute_invoice intra-state (CGST+SGST split)', () => {
    expect(
      r.computeInvoice(
        [
          { quantity: 2, rate: 50000 },
          { quantity: 1, rate: 30000 },
        ],
        { gstRate: 18.0, interState: false },
      ),
    ).toEqual({
      subtotal: 130000,
      igst_amount: 0,
      cgst_amount: 11700,
      sgst_amount: 11700,
      total_tax: 23400,
      total_amount: 153400,
      tds_amount: 0,
      net_receivable: 153400,
    });
  });

  it('compute_invoice inter-state with TDS', () => {
    expect(
      r.computeInvoice([{ quantity: 10, rate: 12345 }], {
        gstRate: 18.0,
        interState: true,
        tdsRate: 10.0,
      }),
    ).toEqual({
      subtotal: 123450,
      igst_amount: 22221,
      cgst_amount: 0,
      sgst_amount: 0,
      total_tax: 22221,
      total_amount: 145671,
      tds_amount: 12345,
      net_receivable: 133326,
    });
  });

  it('compute_invoice odd-paise rounding (half away from zero)', () => {
    expect(
      r.computeInvoice([{ quantity: 1, rate: 33333 }], { gstRate: 5.0, interState: false }),
    ).toEqual({
      subtotal: 33333,
      igst_amount: 0,
      cgst_amount: 833,
      sgst_amount: 833,
      total_tax: 1666,
      total_amount: 34999,
      tds_amount: 0,
      net_receivable: 34999,
    });
  });

  it('ar_aging buckets + skips non-positive', () => {
    expect(
      r.arAging(
        [
          { due_date: '2024-01-01', outstanding_paise: 10000 },
          { due_date: '2024-03-01', outstanding_paise: 20000 },
          { due_date: '2024-04-15', outstanding_paise: 5000 },
          { due_date: '2023-10-01', outstanding_paise: 7000 },
          { due_date: '2024-05-01', outstanding_paise: -500 },
        ],
        '2024-05-01',
      ),
    ).toEqual({
      buckets: { '0-30': 5000, '31-60': 0, '61-90': 20000, '90+': 17000 },
      total_outstanding: 42000,
    });
  });

  it('aging_bucket boundaries', () => {
    expect([0, 30, 31, 90, 91].map(r.agingBucket)).toEqual([
      '0-30',
      '0-30',
      '31-60',
      '61-90',
      '90+',
    ]);
  });

  it('dunning schedule fires exactly on offset days', () => {
    expect(r.dunningDue('2024-05-08', '2024-05-01')).toEqual(['T-7']);
    expect(r.dunningDue('2024-04-30', '2024-05-01')).toEqual(['T+1']);
    expect(r.dunningDue('2024-05-05', '2024-05-01')).toEqual([]);
  });

  it('credit-note deadline + timeliness (CGST s.34)', () => {
    expect(r.creditNoteDeadline('2024-05-15')).toBe('2025-11-30');
    expect(r.creditNoteDeadline('2024-02-15')).toBe('2024-11-30');
    expect(r.isCreditNoteTimely('2024-05-15', '2025-11-30')).toBe(true);
    expect(r.isCreditNoteTimely('2024-05-15', '2025-12-01')).toBe(false);
  });

  it('export invoice — LUT vs IGST-refund + FEMA realisation date', () => {
    expect(r.exportInvoice(1000000, { withLut: true, invoiceDate: '2024-05-15' })).toEqual({
      zero_rated: true,
      with_lut: true,
      igst: 0,
      total: 1000000,
      refund_eligible: false,
      realization_due_date: '2025-02-15',
    });
    expect(
      r.exportInvoice(1000000, { withLut: false, igstRate: 18.0, invoiceDate: '2024-05-31' }),
    ).toEqual({
      zero_rated: true,
      with_lut: false,
      igst: 180000,
      total: 1180000,
      refund_eligible: true,
      realization_due_date: '2025-02-28',
    });
  });

  it('deferred revenue straight-line recognition', () => {
    expect(
      r.deferredRevenueSchedule(120000, { start: '2024-01-01', months: 12, asOf: '2024-04-01' }),
    ).toEqual({ total: 120000, monthly: 10000, months_elapsed: 3, recognized: 30000, deferred: 90000 });

    expect(
      r.deferredRevenueSchedule(100000, { start: '2024-01-01', months: 3, asOf: '2024-12-01' }),
    ).toEqual({ total: 100000, monthly: 33333, months_elapsed: 3, recognized: 100000, deferred: 0 });

    expect(
      r.deferredRevenueSchedule(100000, { start: '2024-01-01', months: 6, asOf: '2023-01-01' }),
    ).toEqual({ total: 100000, monthly: 16667, months_elapsed: 0, recognized: 0, deferred: 100000 });
  });
});
