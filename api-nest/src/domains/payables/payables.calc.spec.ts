/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/payables/payables_calc.py). If the TS port drifts, this fails.
 */
import * as p from './payables.calc';

describe('payables.calc — parity with Python reference', () => {
  it('TDS on payment (sections / thresholds / rounding)', () => {
    expect(p.tdsOnPayment('194C', 5000000, { payee_type: 'individual' })).toEqual({
      applicable: true,
      rate: 1,
      tds_paise: 50000,
    });
    expect(p.tdsOnPayment('194C', 5000000, { payee_type: 'company' })).toEqual({
      applicable: true,
      rate: 2,
      tds_paise: 100000,
    });
    // 20k < 30k single AND agg 30k not crossed -> not applicable
    expect(p.tdsOnPayment('194J', 2000000, { category: 'technical' })).toEqual({
      applicable: false,
      rate: 0,
      tds_paise: 0,
    });
    expect(p.tdsOnPayment('194J', 5000000, { category: 'technical' })).toEqual({
      applicable: true,
      rate: 2,
      tds_paise: 100000,
    });
    expect(p.tdsOnPayment('194J', 5000000)).toEqual({
      applicable: true,
      rate: 10,
      tds_paise: 500000,
    });
    expect(p.tdsOnPayment('194I', 30000000, { category: 'plant' })).toEqual({
      applicable: true,
      rate: 2,
      tds_paise: 600000,
    });
    // aggregate crosses even though single doesn't (10k + 15k ytd >= 20k)
    expect(p.tdsOnPayment('194H', 1000000, { aggregate_ytd: 1500000 })).toEqual({
      applicable: true,
      rate: 2,
      tds_paise: 20000,
    });
    expect(p.tdsOnPayment('194C', 2000000, { payee_type: 'company' })).toEqual({
      applicable: false,
      rate: 0,
      tds_paise: 0,
    });
    // rupee rounding (half up away from zero): 3333350 @10% = 333335p -> ₹3333 -> 333300p
    expect(p.tdsOnPayment('194J', 3333350).tds_paise).toBe(333300);
  });

  it('tds rate lookup', () => {
    expect(p.tdsRate('194C', { payee_type: 'huf' })).toBe(1);
    expect(p.tdsRate('194I', { category: 'building' })).toBe(10);
  });

  it('3-way match', () => {
    expect(p.threeWayMatch(10000000, 10200000, { grn_amount: 10000000 })).toEqual({
      matched: true,
      po_variance_pct: 2.0,
      grn_variance_pct: 2.0,
      max_variance_pct: 2.0,
    });
    expect(p.threeWayMatch(10000000, 10600000, { grn_amount: 10000000 })).toEqual({
      matched: false,
      po_variance_pct: 6.0,
      grn_variance_pct: 6.0,
      max_variance_pct: 6.0,
    });
    expect(p.threeWayMatch(0, 0)).toEqual({
      matched: true,
      po_variance_pct: 0.0,
      grn_variance_pct: 0.0,
      max_variance_pct: 0.0,
    });
    expect(p.threeWayMatch(0, 500)).toEqual({
      matched: false,
      po_variance_pct: 100.0,
      grn_variance_pct: 0.0,
      max_variance_pct: 100.0,
    });
  });

  it('AP aging buckets', () => {
    expect(
      p.apAging(
        [
          { due_date: '2025-06-01', outstanding_paise: 100000 },
          { due_date: '2025-05-01', outstanding_paise: 200000 },
          { due_date: '2025-03-01', outstanding_paise: 300000 },
          { due_date: '2025-01-01', outstanding_paise: 400000 },
          { due_date: '2025-06-15', outstanding_paise: 0 },
        ],
        '2025-07-01',
      ),
    ).toEqual({
      buckets: { '0-30': 100000, '31-60': 0, '61-90': 200000, '90+': 700000 },
      total_outstanding: 1000000,
    });
    expect([p.agingBucket(30), p.agingBucket(31), p.agingBucket(90), p.agingBucket(91)]).toEqual([
      '0-30',
      '31-60',
      '61-90',
      '90+',
    ]);
  });

  it('early-payment discount', () => {
    expect(
      p.earlyPaymentDiscount(10000000, { discount_pct: 2.0, discount_days: 10, paid_in_days: 8 }),
    ).toEqual({ eligible: true, discount: 200000, net_payable: 9800000 });
    expect(
      p.earlyPaymentDiscount(10000000, { discount_pct: 2.0, discount_days: 10, paid_in_days: 15 }),
    ).toEqual({ eligible: false, discount: 0, net_payable: 10000000 });
  });

  it('recurring-vendor detection', () => {
    expect(
      p.detectRecurring([
        { vendor_id: 1, vendor_name: 'SaaSCo', bill_date: '2025-01-05', amount_paise: 100000 },
        { vendor_id: 1, vendor_name: 'SaaSCo', bill_date: '2025-02-04', amount_paise: 105000 },
        { vendor_id: 1, vendor_name: 'SaaSCo', bill_date: '2025-03-06', amount_paise: 98000 },
        { vendor_id: 2, vendor_name: 'OneOff', bill_date: '2025-01-01', amount_paise: 500000 },
      ]),
    ).toEqual([
      {
        vendor_id: 1,
        vendor_name: 'SaaSCo',
        occurrences: 3,
        median_gap_days: 30,
        predicted_amount_paise: 100000,
        predicted_next_date: '2025-04-05',
        category: 'saas_recurring',
      },
    ]);
  });
});
