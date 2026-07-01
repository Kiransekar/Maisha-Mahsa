/**
 * Faithfulness check: every expected value here was produced by the Python reference
 * (api/app/domains/compliance/compliance_calc.py). If the TS port drifts, this fails.
 */
import * as c from './compliance.calc';

describe('compliance.calc — parity with Python reference', () => {
  it('MCA annual-filing deadlines', () => {
    expect(c.mcaDeadlines('2024-09-30')).toEqual([
      { domain: 'roc', form: 'AOC-4', statute: 'Companies Act 2013 s.137', due_date: '2024-10-30' },
      { domain: 'roc', form: 'MGT-7', statute: 'Companies Act 2013 s.92', due_date: '2024-11-29' },
      { domain: 'roc', form: 'DPT-3', statute: 'Companies Act 2013 Rule 16', due_date: '2024-06-30' },
      { domain: 'roc', form: 'DIR-3 KYC', statute: 'Companies Act 2013 Rule 12A', due_date: '2024-09-30' },
    ]);
  });

  it('board-meeting compliance (s.173)', () => {
    expect(c.boardMeetingCompliance(['2024-01-15', '2024-04-10', '2024-07-20', '2024-10-25'])).toEqual(
      { compliant: true, meetings: 4, max_gap_days: 101, reasons: [] },
    );
    expect(c.boardMeetingCompliance(['2024-01-15', '2024-07-20'])).toEqual({
      compliant: false,
      meetings: 2,
      max_gap_days: 187,
      reasons: [
        'fewer than 4 board meetings in the year',
        'gap of 187 days exceeds 120 between consecutive meetings',
      ],
    });
    expect(
      c.boardMeetingCompliance(['2024-01-01', '2024-05-30', '2024-06-15', '2024-12-31']),
    ).toEqual({
      compliant: false,
      meetings: 4,
      max_gap_days: 199,
      reasons: ['gap of 199 days exceeds 120 between consecutive meetings'],
    });
  });

  it('secretarial calendar (FY end 2024-03-31, day-clamp + month math)', () => {
    expect(c.secretarialCalendar('2024-03-31')).toEqual([
      { item: 'Annual General Meeting', statute: 'Companies Act 2013 s.96', due_date: '2024-09-30' },
      { item: 'Maintain statutory registers', statute: 'Companies Act 2013 s.88', due_date: '2024-03-31' },
      { item: 'Record minutes of meetings', statute: 'Companies Act 2013 s.118', due_date: '2024-03-31' },
      { item: 'Board meeting Q1', statute: 'Companies Act 2013 s.173', due_date: '2023-06-30' },
      { item: 'Board meeting Q2', statute: 'Companies Act 2013 s.173', due_date: '2023-09-30' },
      { item: 'Board meeting Q3', statute: 'Companies Act 2013 s.173', due_date: '2023-12-31' },
      { item: 'Board meeting Q4', statute: 'Companies Act 2013 s.173', due_date: '2024-03-31' },
    ]);
  });

  it('addMonths day clamping (Jan 31 + 1 month = Feb 29 leap)', () => {
    expect(c.addMonths('2024-01-31', 1)).toBe('2024-02-29');
    expect(c.addMonths('2024-03-31', -12)).toBe('2023-03-31');
  });

  it('audit support package (4/12 present -> 33.3%)', () => {
    expect(
      c.auditSupportPackage(['trial_balance', 'general_ledger', 'bank_statements', 'gst_returns']),
    ).toEqual({
      audit_type: 'statutory',
      items: [
        { item: 'trial_balance', present: true },
        { item: 'general_ledger', present: true },
        { item: 'bank_statements', present: true },
        { item: 'bank_reconciliation', present: false },
        { item: 'fixed_asset_register', present: false },
        { item: 'gst_returns', present: true },
        { item: 'tds_returns', present: false },
        { item: 'payroll_records', present: false },
        { item: 'invoices', present: false },
        { item: 'bills', present: false },
        { item: 'board_minutes', present: false },
        { item: 'cap_table', present: false },
      ],
      missing: [
        'bank_reconciliation', 'fixed_asset_register', 'tds_returns', 'payroll_records',
        'invoices', 'bills', 'board_minutes', 'cap_table',
      ],
      readiness_pct: 33.3,
    });
  });

  it('DPIIT eligibility', () => {
    expect(
      c.dpiitEligibility({
        incorporationDate: '2020-01-01',
        asOf: '2024-06-01',
        annualTurnoverPaise: 5000000000,
      }),
    ).toEqual({ eligible: true, age_years: 4.42, reasons: [] });

    expect(
      c.dpiitEligibility({
        incorporationDate: '2010-01-01',
        asOf: '2024-06-01',
        annualTurnoverPaise: 100,
      }),
    ).toEqual({ eligible: false, age_years: 14.41, reasons: ['incorporated 10 or more years ago'] });

    expect(
      c.dpiitEligibility({
        incorporationDate: '2020-01-01',
        asOf: '2024-06-01',
        annualTurnoverPaise: 1e13,
        isReconstituted: true,
      }),
    ).toEqual({
      eligible: false,
      age_years: 4.42,
      reasons: [
        'annual turnover is Rs.100 crore or more',
        'formed by splitting up / reconstructing an existing business',
      ],
    });
  });

  it('overdue / health / alerts (as_of 2024-06-13)', () => {
    const entries: c.Entry[] = [
      { domain: 'gst', form_name: 'GSTR-3B', due_date: '2024-06-20', status: 'pending' },
      { domain: 'tds', form_name: 'TDS', due_date: '2024-06-07', status: 'filed' },
      { domain: 'pf', form_name: 'PF', due_date: '2024-06-15', status: 'pending' },
      { domain: 'roc', form_name: 'AOC-4', due_date: '2024-05-01', status: 'pending' },
    ];
    expect(c.overdueCount(entries, '2024-06-13')).toBe(1);
    expect(c.domainHealth(entries, '2024-06-13')).toEqual({
      roc: 0.0, gst: 1.0, tds: 1.0, pf: 1.0, esi: 1.0, pt: 1.0,
    });
    expect(c.alerts(entries, '2024-06-13')).toEqual([
      { domain: 'gst', form_name: 'GSTR-3B', due_date: '2024-06-20', label: 'T-7', days_to_due: 7 },
      { domain: 'roc', form_name: 'AOC-4', due_date: '2024-05-01', label: 'OVERDUE', days_overdue: 43 },
    ]);
  });
});
