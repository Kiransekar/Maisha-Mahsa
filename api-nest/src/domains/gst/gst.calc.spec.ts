/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/gst/gst_calc.py). If the TS port drifts, this fails.
 */
import * as g from './gst.calc';

describe('gst.calc — parity with Python reference', () => {
  it('GSTIN validation + check digit', () => {
    expect(g.validateGstin('27AAPFU0939F1ZV')).toBe(true);
    expect(g.validateGstin('27AAPFU0939F1ZX')).toBe(false);
    expect(g.gstinCheckDigit('27AAPFU0939F1Z')).toBe('V');
  });

  it('ITC set-off (statutory order)', () => {
    const r = g.itcSetoff(
      { igst: 100000, cgst: 50000, sgst: 50000 },
      { igst: 120000, cgst: 20000, sgst: 10000 },
    );
    expect(r.cash).toEqual({ igst: 0, cgst: 10000, sgst: 40000 });
    expect(r.remaining_credit).toEqual({ igst: 0, cgst: 0, sgst: 0 });
  });

  it('late fee + interest', () => {
    expect(g.lateFee3b(10)).toBe(50000);
    expect(g.lateFee3b(10, true)).toBe(20000);
    expect(g.lateFee3b(10000)).toBe(1000000);
    expect(g.interest3b(1000000, 30)).toBe(14800);
  });

  it('GSTR-3B end to end', () => {
    const r = g.computeGstr3b(
      { igst: 100000, cgst: 50000, sgst: 50000 },
      { igst: 120000, cgst: 20000, sgst: 10000 },
      { daysLate: 10 },
    );
    expect(r).toEqual({
      cash: { igst: 0, cgst: 10000, sgst: 40000 },
      cash_total: 50000,
      remaining_credit: { igst: 0, cgst: 0, sgst: 0 },
      late_fee: 50000,
      interest: 200,
      total_payable: 100200,
    });
  });

  it('composition tax', () => {
    expect(g.compositionTax(10000000, 'trader')).toEqual({
      category: 'trader',
      rate_pct: 1,
      turnover: 10000000,
      tax: 100000,
    });
  });

  it('e-invoice IRN (NIC SHA-256)', () => {
    expect(g.computeIrn('27AAPFU0939F1ZV', { docNo: 'INV/2024/001', docDate: '2024-05-15' })).toBe(
      'eb4b008b07cc50c1926cbf776507596fad894f720ae4ff5c20dacd9008428138',
    );
  });

  it('GSTR-1 outward summary', () => {
    const r = g.buildGstr1(
      [
        { invoice_no: 'A1', taxable: 100000, igst: 18000, hsn: '1234', gstin: '27AAPFU0939F1ZV' },
        { invoice_no: 'A2', taxable: 50000, cgst: 4500, sgst: 4500, hsn: '5678' },
      ],
      '2024-05',
    );
    expect(r.b2b).toEqual({
      '27AAPFU0939F1ZV': [{ invoice_no: 'A1', taxable: 100000, igst: 18000, cgst: 0, sgst: 0 }],
    });
    expect(r.b2c).toEqual({ taxable: 50000, igst: 0, cgst: 4500, sgst: 4500 });
    expect(r.totals).toEqual({ taxable: 150000, igst: 18000, cgst: 4500, sgst: 4500, total_tax: 27000 });
    expect(r.errors).toEqual([]);
  });
});
