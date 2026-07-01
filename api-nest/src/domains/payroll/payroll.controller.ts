/** Payroll routes (thin — delegate to the service and the loop). Mirrors app/domains/payroll/router.py. */
import { Body, Controller, Get, Param, ParseIntPipe, Post, Query, StreamableFile } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { computeComponents } from './payroll.calc';
import { NewEmployeeDto, SalaryInputDto } from './payroll.dto';
import { PayrollService } from './payroll.service';

@ApiTags('payroll')
@Controller('api/payroll')
export class PayrollController {
  constructor(
    private readonly service: PayrollService,
    private readonly loop: LoopService,
  ) {}

  @Post('employees')
  createEmployee(@Body() body: NewEmployeeDto) {
    return this.service.createEmployee(body);
  }

  @Post('employees/:employee_id/salary')
  async setSalary(
    @Param('employee_id', ParseIntPipe) employeeId: number,
    @Body() body: SalaryInputDto,
  ) {
    const structure = await this.service.setSalaryStructure(employeeId, body);
    return {
      structure_id: structure.id,
      gross_salary: structure.gross_salary,
      employee_pf: structure.employee_pf,
      employee_esi: structure.employee_esi,
      professional_tax: structure.professional_tax,
      tds_monthly: structure.tds_monthly,
      net_salary: structure.net_salary,
      ctc: structure.ctc,
    };
  }

  /** Compute a salary breakdown without persisting — useful for offer modelling. */
  @Get('preview')
  preview(
    @Query('basic', ParseIntPipe) basic: number,
    @Query('hra', ParseIntPipe) hra: number,
    @Query('lta') lta?: string,
    @Query('special_allowance') specialAllowance?: string,
    @Query('state') state?: string,
    @Query('month') month?: string,
  ) {
    return computeComponents({
      basic,
      hra,
      lta: lta ? parseInt(lta, 10) : 0,
      special_allowance: specialAllowance ? parseInt(specialAllowance, 10) : 0,
      state: state ?? null,
      month: month ? parseInt(month, 10) : 1,
    });
  }

  /** Monthly payslip PDF for an employee. `period` = YYYY-MM. */
  @Get('employees/:employee_id/payslip')
  async payslip(
    @Param('employee_id', ParseIntPipe) employeeId: number,
    @Query('period') period: string,
    @Query('company') company?: string,
  ): Promise<StreamableFile> {
    const pdf = await this.service.payslipPdf(employeeId, period, company ?? undefined);
    return new StreamableFile(pdf, { type: 'application/pdf', disposition: `inline; filename="payslip-${employeeId}-${period}.pdf"` });
  }

  /** Form 16 Part B PDF for an employee. `fy` = YYYY-YY. */
  @Get('employees/:employee_id/form16')
  async form16(
    @Param('employee_id', ParseIntPipe) employeeId: number,
    @Query('fy') fy: string,
    @Query('company') company?: string,
    @Query('tan') tan?: string,
  ): Promise<StreamableFile> {
    const pdf = await this.service.form16Pdf(employeeId, fy, company ?? undefined, tan);
    return new StreamableFile(pdf, { type: 'application/pdf', disposition: `inline; filename="form16-${employeeId}-${fy}.pdf"` });
  }

  @Post('runs')
  runPayroll(@Query('month_year') monthYear: string) {
    const runDate = new Date().toISOString().slice(0, 10);
    return this.service.runPayroll(monthYear, runDate);
  }

  /** Fold the payroll snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'payroll.fold',
    });
    return {
      snapshot: outcome.snapshot,
      validation: outcome.fold.validation,
      shape: outcome.fold.shape,
      domain_intent: outcome.fold.domain_intent,
      audit_hash: outcome.auditHash,
    };
  }
}
