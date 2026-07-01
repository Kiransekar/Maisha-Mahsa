/**
 * Faithfulness check: every expected value here was produced by the Python reference
 * (api/app/domains/payroll/statutory.py + ecr.py + service.compute_components).
 * If the TS port drifts, this fails.
 */
import * as p from './payroll.calc';

describe('payroll.calc — parity with Python reference', () => {
  it('PF (EPF) contributions', () => {
    expect(p.pfWage(1500000)).toBe(1500000);
    expect(p.pfWage(2000000)).toBe(1500000); // capped at ₹15,000
    expect(p.pfEmployee(1500000)).toBe(180000);
    expect(p.pfEmployee(2000000)).toBe(180000);
    expect(p.pfEmployee(1234500)).toBe(148100);
    expect(p.epsEmployer(1500000)).toBe(125000);
    expect(p.epsEmployer(1000000)).toBe(83300);
    expect(p.epfEmployerDiff(1500000)).toBe(55000);
  });

  it('ESI (ceil to rupee, nil above ceiling)', () => {
    expect(p.esi(1800000)).toEqual([13500, 58500]);
    expect(p.esi(2200000)).toEqual([0, 0]);
    expect(p.esi(1234567)).toEqual([9300, 40200]);
  });

  it('Professional Tax (state slabs + MH Feb special)', () => {
    expect(p.professionalTax('MH', 1500000, 1)).toBe(20000);
    expect(p.professionalTax('MH', 1500000, 2)).toBe(30000); // February ₹300
    expect(p.professionalTax('MH', 700000, 1)).toBe(0);
    expect(p.professionalTax('MH', 900000, 1)).toBe(17500);
    expect(p.professionalTax('KA', 3000000, 1)).toBe(20000);
    expect(p.professionalTax('KA', 2000000, 1)).toBe(0);
    expect(p.professionalTax('WB', 3000000, 1)).toBe(15000);
    expect(p.professionalTax('XX', 3000000, 1)).toBe(0);
    expect(p.professionalTax(null, 3000000, 1)).toBe(0);
  });

  it('Labour Welfare Fund (state calendars)', () => {
    expect(p.labourWelfareFund('MH', 6)).toEqual([2500, 7500]);
    expect(p.labourWelfareFund('MH', 1)).toEqual([0, 0]);
    expect(p.labourWelfareFund('KA', 12)).toEqual([2000, 4000]);
    expect(p.labourWelfareFund('XX', 6)).toEqual([0, 0]);
  });

  it('loss of pay + leave balance', () => {
    expect(p.lossOfPay(3000000, 3, 30)).toBe(300000);
    expect(p.lossOfPay(3000000, 0, 30)).toBe(0);
    expect(p.lossOfPay(2500000, 2, 31)).toBe(161300);
    expect(p.lossOfPay(3000000, 45, 30)).toBe(3000000); // capped at full month
    expect(p.leaveBalance(12.0, 1.5, 4.0)).toBe(9.5);
  });

  it('TDS / annual income tax (new regime, cess, rebate, marginal relief)', () => {
    expect(p.annualIncomeTax(1000000)).toBe(0); // below rebate
    expect(p.annualIncomeTax(120000000)).toBe(0); // == 12L rebate limit
    expect(p.annualIncomeTax(150000000)).toBe(10920000); // ₹15L
    expect(p.annualIncomeTax(50000000)).toBe(0);
    expect(p.annualIncomeTax(121000000)).toBe(1040000); // marginal relief zone
    expect(p.monthlyTds(12000000)).toBe(0);
    expect(p.monthlyTds(180000000)).toBe(1256700);
    expect(p.monthlyTds(120000000)).toBe(0);
  });

  it('gratuity + bonus provisions', () => {
    expect(p.gratuityRequired(5000000, 5)).toBe(14423100);
    expect(p.gratuityRequired(5000000, 0)).toBe(0);
    expect(p.gratuityRequired(1234500, 7)).toBe(4985500);
    expect(p.bonusProvisionMonthly(700000)).toBe(58300);
    expect(p.bonusProvisionMonthly(1500000)).toBe(58300);
    expect(p.bonusProvisionMonthly(2500000)).toBe(0); // above ₹21,000 eligibility
    expect(p.bonusProvisionMonthly(500000)).toBe(41700);
  });

  it('computeComponents — full monthly breakdown', () => {
    expect(
      p.computeComponents({
        basic: 1500000, hra: 600000, lta: 100000, special_allowance: 300000,
        state: 'MH', month: 1,
      }),
    ).toEqual({
      gross_salary: 2500000, basic: 1500000, hra: 600000, lta: 100000, special_allowance: 300000,
      employee_pf: 180000, employer_pf: 180000, employee_esi: 0, employer_esi: 0,
      professional_tax: 20000, tds_monthly: 0, loss_of_pay: 0, lop_days: 0,
      employee_deductions: 200000, net_salary: 2300000, ctc: 2680000,
    });
  });

  it('computeComponents — MH February PT special', () => {
    const c = p.computeComponents({
      basic: 1500000, hra: 600000, lta: 100000, special_allowance: 300000, state: 'MH', month: 2,
    });
    expect(c.professional_tax).toBe(30000);
    expect(c.employee_deductions).toBe(210000);
    expect(c.net_salary).toBe(2290000);
  });

  it('computeComponents — ESI applicable + Karnataka PT', () => {
    expect(
      p.computeComponents({
        basic: 800000, hra: 400000, lta: 0, special_allowance: 200000, state: 'KA', month: 1,
      }),
    ).toEqual({
      gross_salary: 1400000, basic: 800000, hra: 400000, lta: 0, special_allowance: 200000,
      employee_pf: 96000, employer_pf: 96000, employee_esi: 10500, employer_esi: 45500,
      professional_tax: 0, tds_monthly: 0, loss_of_pay: 0, lop_days: 0,
      employee_deductions: 106500, net_salary: 1293500, ctc: 1541500,
    });
  });

  it('computeComponents — real TDS', () => {
    const c = p.computeComponents({
      basic: 10000000, hra: 4000000, lta: 1000000, special_allowance: 5000000,
      state: 'KA', month: 6,
    });
    expect(c.tds_monthly).toBe(2437500);
    expect(c.employee_deductions).toBe(2637500);
    expect(c.net_salary).toBe(17362500);
    expect(c.ctc).toBe(20180000);
  });

  it('computeComponents — loss of pay', () => {
    const c = p.computeComponents({
      basic: 1500000, hra: 600000, lta: 100000, special_allowance: 300000,
      state: null, month: 4, lop_days: 3, days_in_month: 30,
    });
    expect(c.loss_of_pay).toBe(250000);
    expect(c.employee_deductions).toBe(430000);
    expect(c.net_salary).toBe(2070000);
  });

  it('EPFO ECR text builder', () => {
    const m: p.EcrMember = {
      uan: '100200300400', member_name: 'Asha Rao', gross_wages: 25000, epf_wages: 15000,
      eps_wages: 15000, edli_wages: 15000, epf_contri_remitted: 1800, eps_contri_remitted: 1250,
      epf_eps_diff_remitted: 550,
    };
    expect(p.ecrLine(m)).toBe(
      '100200300400#~#Asha Rao#~#25000#~#15000#~#15000#~#15000#~#1800#~#1250#~#550#~#0#~#0',
    );
    expect(p.buildEcr([m, m])).toBe(p.ecrLine(m) + '\n' + p.ecrLine(m));
  });
});
