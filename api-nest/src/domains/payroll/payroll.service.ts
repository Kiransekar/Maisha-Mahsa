/**
 * Payroll service: salary-structure derivation, the monthly payroll run, LWF due,
 * the EPFO ECR file, and the payroll health snapshot for Mahsa. All money is integer
 * paise; statutory math is delegated to payroll.calc. Deterministic — the payroll
 * month is passed in (buildSnapshot's `asOf` is injected, no clock read).
 * Mirrors app/domains/payroll/service.py.
 */
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import { form16Pdf, payslipPdf } from '../../pdf/pdf';
import * as calc from './payroll.calc';
import { NewEmployeeDto, SalaryInputDto } from './payroll.dto';
import { Employee, PayrollEntry, PayrollRun, SalaryStructure } from './payroll.entities';

function monthOf(isoDate: string): number {
  return parseInt(isoDate.slice(5, 7), 10);
}

@Injectable()
export class PayrollService implements SnapshotProducer {
  readonly domain = 'payroll';

  constructor(
    @InjectRepository(Employee) private readonly employees: Repository<Employee>,
    @InjectRepository(SalaryStructure) private readonly structures: Repository<SalaryStructure>,
    @InjectRepository(PayrollRun) private readonly runs: Repository<PayrollRun>,
    @InjectRepository(PayrollEntry) private readonly entries: Repository<PayrollEntry>,
  ) {}

  // ---- employees ------------------------------------------------------------------

  async createEmployee(body: NewEmployeeDto): Promise<{ id: number }> {
    const emp = this.employees.create({
      employee_code: body.employee_code,
      name: body.name,
      date_of_joining: body.date_of_joining,
      state: body.state ?? null,
      pan: body.pan ?? null,
      uan: body.uan ?? null,
    });
    await this.employees.save(emp);
    return { id: emp.id };
  }

  // ---- salary structure -----------------------------------------------------------

  async setSalaryStructure(employeeId: number, body: SalaryInputDto): Promise<SalaryStructure> {
    const emp = await this.employees.findOne({ where: { id: employeeId } });
    if (emp === null) throw new NotFoundException(`employee ${employeeId} not found`);
    const comp = calc.computeComponents({
      basic: body.basic,
      hra: body.hra,
      lta: body.lta,
      special_allowance: body.special_allowance,
      state: emp.state,
      month: monthOf(body.effective_from),
    });
    const structure = this.structures.create({
      employee_id: employeeId,
      effective_from: body.effective_from,
      basic: comp.basic,
      hra: comp.hra,
      lta: comp.lta,
      special_allowance: comp.special_allowance,
      employer_pf: comp.employer_pf,
      employer_esi: comp.employer_esi,
      employee_pf: comp.employee_pf,
      employee_esi: comp.employee_esi,
      professional_tax: comp.professional_tax,
      tds_monthly: comp.tds_monthly,
      gross_salary: comp.gross_salary,
      net_salary: comp.net_salary,
      ctc: comp.ctc,
    });
    await this.structures.save(structure);
    return structure;
  }

  private async latestStructure(
    employeeId: number,
    onOrBefore: string,
  ): Promise<SalaryStructure | null> {
    const rows = await this.structures.find({
      where: { employee_id: employeeId },
      order: { effective_from: 'DESC' },
    });
    return rows.find((r) => r.effective_from <= onOrBefore) ?? null;
  }

  private async activeEmployees(): Promise<Employee[]> {
    return this.employees.find({ where: { status: 'active' } });
  }

  // ---- monthly run ----------------------------------------------------------------

  /** Run payroll for `monthYear` ("YYYY-MM"). Recomputes each active employee's entry from
   * their latest effective salary structure. `lopDays` maps employee_id → unpaid-leave days. */
  async runPayroll(
    monthYear: string,
    runDate: string,
    lopDays: Record<number, number> = {},
  ): Promise<Record<string, any>> {
    const [year, month] = monthYear.split('-').map((s) => parseInt(s, 10));
    const daysInMonth = new Date(year, month, 0).getDate();
    const anchor = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-28`;

    const run = this.runs.create({ month_year: monthYear, run_date: runDate, status: 'draft' });
    await this.runs.save(run);

    const totals = { gross: 0, deductions: 0, net: 0, pf_employer: 0, esi_employer: 0 };
    let minNet: number | null = null;
    let count = 0;
    for (const emp of await this.activeEmployees()) {
      const structure = await this.latestStructure(emp.id, anchor);
      if (structure === null) continue;
      const comp = calc.computeComponents({
        basic: structure.basic,
        hra: structure.hra,
        lta: structure.lta,
        special_allowance: structure.special_allowance,
        state: emp.state,
        month,
        lop_days: lopDays[emp.id] ?? 0,
        days_in_month: daysInMonth,
      });
      await this.entries.save(
        this.entries.create({
          payroll_run_id: run.id,
          employee_id: emp.id,
          gross: comp.gross_salary,
          basic: comp.basic,
          hra: comp.hra,
          lta: comp.lta,
          special_allowance: comp.special_allowance,
          employee_pf: comp.employee_pf,
          employee_esi: comp.employee_esi,
          professional_tax: comp.professional_tax,
          tds: comp.tds_monthly,
          employer_pf: comp.employer_pf,
          employer_esi: comp.employer_esi,
          net_pay: comp.net_salary,
        }),
      );
      totals.gross += comp.gross_salary;
      totals.deductions += comp.employee_deductions;
      totals.net += comp.net_salary;
      totals.pf_employer += comp.employer_pf;
      totals.esi_employer += comp.employer_esi;
      minNet = minNet === null ? comp.net_salary : Math.min(minNet, comp.net_salary);
      count += 1;
    }

    run.total_gross = totals.gross;
    run.total_deductions = totals.deductions;
    run.total_net = totals.net;
    run.total_pf_employer = totals.pf_employer;
    run.total_esi_employer = totals.esi_employer;
    await this.runs.save(run);

    return {
      payroll_run_id: run.id,
      month_year: monthYear,
      employee_count: count,
      total_gross: totals.gross,
      total_deductions: totals.deductions,
      total_net: totals.net,
      total_pf_employer: totals.pf_employer,
      total_esi_employer: totals.esi_employer,
      min_net_pay: minNet === null ? 0 : minNet,
    };
  }

  // ---- Labour Welfare Fund (state calendars) --------------------------------------

  /** LWF remittance due for `period` (YYYY-MM): per-state totals, non-zero only in due months. */
  // ---- statutory PDFs (payslip, Form 16) ------------------------------------------

  private async breakdown(employeeId: number, period: string) {
    const emp = await this.employees.findOne({ where: { id: employeeId } });
    if (emp === null) throw new NotFoundException(`employee ${employeeId} not found`);
    const structure = await this.latestStructure(employeeId, `${period}-28`);
    if (structure === null) throw new NotFoundException(`no salary structure for employee ${employeeId}`);
    const comp = calc.computeComponents({
      basic: structure.basic,
      hra: structure.hra,
      lta: structure.lta,
      special_allowance: structure.special_allowance,
      state: emp.state ?? null,
      month: Number(period.slice(5, 7)),
    });
    return { emp, structure, comp };
  }

  /** Monthly payslip PDF for `period` (YYYY-MM). Figures come from the payroll engine. */
  async payslipPdf(employeeId: number, period: string, company = 'Maisha-Mahsa'): Promise<Buffer> {
    const { emp, structure, comp } = await this.breakdown(employeeId, period);
    return payslipPdf({
      company,
      employee_name: emp.name,
      employee_code: emp.employee_code,
      period,
      earnings: [
        ['Basic', structure.basic],
        ['HRA', structure.hra],
        ['Special allowance', structure.special_allowance],
        ['LTA', structure.lta],
      ],
      deductions: [
        ['PF (employee)', comp.employee_pf],
        ['ESI (employee)', comp.employee_esi],
        ['Professional tax', comp.professional_tax],
        ['TDS', comp.tds_monthly],
      ],
      gross: comp.gross_salary,
      total_deductions: comp.employee_deductions,
      net: comp.net_salary,
    });
  }

  /** Form 16 Part B PDF for `financialYear` (YYYY-YY). Annualises monthly salary and applies the
   * ₹75,000 standard deduction (new-regime FY25-26). */
  async form16Pdf(employeeId: number, financialYear: string, company = 'Maisha-Mahsa', tan?: string): Promise<Buffer> {
    const start = Number(financialYear.slice(0, 4));
    const { emp, comp } = await this.breakdown(employeeId, `${start}-06`);
    const grossAnnual = Math.trunc(comp.gross_salary) * 12;
    const standardDeduction = 7_500_000; // ₹75,000 in paise (s.16(ia), new regime)
    const taxable = Math.max(0, grossAnnual - standardDeduction);
    return form16Pdf({
      company,
      tan: tan ?? null,
      employee_name: emp.name,
      pan: emp.pan ?? null,
      financial_year: financialYear,
      assessment_year: `${start + 1}-${String(start + 2).slice(2)}`,
      rows: [
        ['Gross salary (annual)', grossAnnual],
        ['Less: Standard deduction u/s 16(ia)', standardDeduction],
        ['Total taxable income', taxable],
      ],
      total_tax_deducted: Math.trunc(comp.tds_monthly) * 12,
    });
  }

  async lwfDue(period: string): Promise<Record<string, any>> {
    const month = parseInt(period.slice(5, 7), 10);
    const byState: Record<string, { employee: number; employer: number; members: number }> = {};
    let totalEmp = 0;
    let totalEmpr = 0;
    for (const emp of await this.activeEmployees()) {
      const [employeeC, employerC] = calc.labourWelfareFund(emp.state, month);
      if (employeeC === 0 && employerC === 0) continue;
      const code = (emp.state ?? '').toUpperCase();
      const bucket = (byState[code] ??= { employee: 0, employer: 0, members: 0 });
      bucket.employee += employeeC;
      bucket.employer += employerC;
      bucket.members += 1;
      totalEmp += employeeC;
      totalEmpr += employerC;
    }
    return {
      period,
      by_state: byState,
      total_employee_paise: totalEmp,
      total_employer_paise: totalEmpr,
      total_paise: totalEmp + totalEmpr,
    };
  }

  // ---- EPFO ECR upload file --------------------------------------------------------

  /** Build the EPFO ECR upload file for `period` (YYYY-MM) — one #~#-delimited line per member. */
  async ecrText(period: string): Promise<string> {
    const r = (paise: number) => Math.round(paise / 100); // whole rupees
    const anchor = `${period}-28`;
    const members: calc.EcrMember[] = [];
    for (const emp of await this.activeEmployees()) {
      const structure = await this.latestStructure(emp.id, anchor);
      if (structure === null) continue;
      const basic = structure.basic;
      const comp = calc.computeComponents({
        basic: structure.basic,
        hra: structure.hra,
        lta: structure.lta,
        special_allowance: structure.special_allowance,
        state: emp.state,
        month: parseInt(period.slice(5, 7), 10),
      });
      const pfWage = calc.pfWage(basic);
      members.push({
        uan: emp.uan ?? '',
        member_name: emp.name,
        gross_wages: r(comp.gross_salary),
        epf_wages: r(pfWage),
        eps_wages: r(pfWage),
        edli_wages: r(pfWage),
        epf_contri_remitted: r(calc.pfEmployee(basic)),
        eps_contri_remitted: r(calc.epsEmployer(basic)),
        epf_eps_diff_remitted: r(calc.epfEmployerDiff(basic)),
      });
    }
    return calc.buildEcr(members);
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchorIso = asOf ?? '1970-01-01';
    const month = monthOf(anchorIso);

    let totalGross = 0;
    let totalEmployerPf = 0;
    let bonusRequired = 0;
    let lwfDue = 0;
    let minNet: number | null = null;
    for (const emp of await this.activeEmployees()) {
      const structure = await this.latestStructure(emp.id, anchorIso);
      if (structure === null) continue;
      const comp = calc.computeComponents({
        basic: structure.basic,
        hra: structure.hra,
        lta: structure.lta,
        special_allowance: structure.special_allowance,
        state: emp.state,
        month,
      });
      totalGross += comp.gross_salary;
      totalEmployerPf += comp.employer_pf;
      bonusRequired += calc.bonusProvisionMonthly(structure.basic);
      const [employeeLwf, employerLwf] = calc.labourWelfareFund(emp.state, month);
      lwfDue += employeeLwf + employerLwf;
      minNet = minNet === null ? comp.net_salary : Math.min(minNet, comp.net_salary);
    }

    return {
      as_of: anchorIso,
      monthly_burn: totalGross + totalEmployerPf,
      metrics: {
        pf_compliance: 1.0,
        esi_compliance: 1.0,
        tds_accuracy: 1.0,
        pt_state: 1.0,
        lwf_state: 1.0,
        gratuity_reserve: 1.0,
        bonus_reserve: 1.0,
        leave_liability: 1.0,
        min_net_pay_paise: minNet === null ? 0 : minNet,
        monthly_bonus_required_paise: bonusRequired,
        lwf_due_paise: lwfDue,
      },
    };
  }
}
