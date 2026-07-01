import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';

import { buildDataSourceOptions } from './db/data-source';
import { CoreModule } from './core/core.module';
import { AuthModule } from './auth/auth.controller';
import { HealthModule } from './health/health.controller';
import { SchedulerModule } from './scheduler/scheduler.module';
import { GstModule } from './domains/gst/gst.module';
import { LedgerModule } from './domains/ledger/ledger.module';
import { TreasuryModule } from './domains/treasury/treasury.module';
import { PayrollModule } from './domains/payroll/payroll.module';
import { RevenueModule } from './domains/revenue/revenue.module';
import { ExpenseModule } from './domains/expense/expense.module';
import { PayablesModule } from './domains/payables/payables.module';
import { ForecastModule } from './domains/forecast/forecast.module';
import { EquityModule } from './domains/equity/equity.module';
import { TaxModule } from './domains/tax/tax.module';
import { ComplianceModule } from './domains/compliance/compliance.module';
import { VaultModule } from './domains/vault/vault.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, envFilePath: '.env' }),
    TypeOrmModule.forRoot(buildDataSourceOptions()),
    CoreModule,
    AuthModule,
    HealthModule,
    SchedulerModule,
    // Domain modules — one per PRD domain (all 12).
    GstModule,
    LedgerModule,
    TreasuryModule,
    PayrollModule,
    RevenueModule,
    ExpenseModule,
    PayablesModule,
    ForecastModule,
    EquityModule,
    TaxModule,
    ComplianceModule,
    VaultModule,
  ],
})
export class AppModule {}
