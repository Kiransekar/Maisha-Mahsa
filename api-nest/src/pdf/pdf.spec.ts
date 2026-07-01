import { payslipPdf, form16Pdf } from './pdf';

describe('statutory PDFs', () => {
  it('payslipPdf emits a valid PDF', async () => {
    const buf = await payslipPdf({
      company: 'Acme',
      employee_name: 'Ravi',
      employee_code: 'E1',
      period: '2024-05',
      earnings: [['Basic', 5000000], ['HRA', 2000000]],
      deductions: [['PF (employee)', 600000], ['TDS', 300000]],
      gross: 7000000,
      total_deductions: 900000,
      net: 6100000,
    });
    expect(buf.subarray(0, 5).toString()).toBe('%PDF-');
    expect(buf.length).toBeGreaterThan(500);
  });

  it('form16Pdf emits a valid PDF', async () => {
    const buf = await form16Pdf({
      company: 'Acme',
      tan: 'ABCD12345E',
      employee_name: 'Ravi',
      pan: 'ABCDE1234F',
      financial_year: '2024-25',
      assessment_year: '2025-26',
      rows: [['Gross salary (annual)', 84000000], ['Less: Standard deduction u/s 16(ia)', 7500000], ['Total taxable income', 76500000]],
      total_tax_deducted: 3600000,
    });
    expect(buf.subarray(0, 5).toString()).toBe('%PDF-');
  });
});
