/**
 * Treasury service: bank-CSV import and the cash / burn / runway math.
 * Exact paise; deterministic. Time is injected (`asOf`) — no clock read.
 * Mirrors api/app/domains/treasury/service.py.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as calc from './treasury.calc';
import { BankAccount, BankTransaction } from './treasury.entities';

@Injectable()
export class TreasuryService implements SnapshotProducer {
  readonly domain = 'treasury';

  constructor(
    @InjectRepository(BankAccount) private readonly accounts: Repository<BankAccount>,
    @InjectRepository(BankTransaction) private readonly txns: Repository<BankTransaction>,
  ) {}

  async createAccount(body: {
    bank_name: string;
    account_number: string;
    ifsc: string;
    opening_balance_paise?: number;
  }): Promise<{ id: number }> {
    const opening = body.opening_balance_paise ?? 0;
    const acct = this.accounts.create({
      bank_name: body.bank_name,
      account_number: body.account_number,
      ifsc: body.ifsc,
      opening_balance: opening,
      current_balance: opening,
    });
    await this.accounts.save(acct);
    return { id: acct.id };
  }

  // ---- CSV import ----------------------------------------------------------------

  /**
   * Import a bank statement CSV into bank_transactions and update the account balance.
   * Returns counts + closing balance (paise). Faithful port of import_csv.
   */
  async importCsv(accountId: number, csvText: string) {
    const account = await this.accounts.findOne({ where: { id: accountId } });
    if (account === null) throw new Error(`bank account ${accountId} not found`);

    const rows = parseCsv(csvText).filter((r) => r.some((c) => c.trim() !== ''));
    if (rows.length === 0) {
      return {
        account_id: accountId,
        rows_imported: 0,
        rows_skipped: 0,
        closing_balance_paise: account.current_balance,
      };
    }

    const cols = calc.resolveColumns(rows[0]);
    let imported = 0;
    let skipped = 0;
    let running = account.current_balance;
    const toSave: BankTransaction[] = [];

    for (const row of rows.slice(1)) {
      const dateRaw = calc.cell(row, cols, 'date');
      const txnDate = dateRaw ? calc.parseDate(dateRaw) : null;
      if (txnDate === null) {
        skipped += 1;
        continue;
      }

      const debitRaw = calc.cell(row, cols, 'debit');
      const creditRaw = calc.cell(row, cols, 'credit');
      const debit = debitRaw ? calc.parseAmount(debitRaw) : 0;
      const credit = creditRaw ? calc.parseAmount(creditRaw) : 0;
      if (debit === 0 && credit === 0) {
        skipped += 1;
        continue;
      }

      running = running + credit - debit;
      let balance = running;
      const balanceRaw = calc.cell(row, cols, 'balance');
      if (balanceRaw) {
        const parsedBal = calc.parseAmount(balanceRaw);
        if (parsedBal !== 0) {
          balance = parsedBal;
          running = parsedBal;
        }
      }

      toSave.push(
        this.txns.create({
          account_id: accountId,
          txn_date: txnDate,
          description: calc.cell(row, cols, 'description'),
          reference: calc.cell(row, cols, 'reference'),
          debit,
          credit,
          balance,
        }),
      );
      imported += 1;
    }

    if (toSave.length) await this.txns.save(toSave);
    account.current_balance = running;
    await this.accounts.save(account);

    return {
      account_id: accountId,
      rows_imported: imported,
      rows_skipped: skipped,
      closing_balance_paise: running,
    };
  }

  // ---- metrics -------------------------------------------------------------------

  async cashPosition() {
    const accounts = await this.accounts.find();
    const byAccount: Record<string, number> = {};
    for (const a of accounts) byAccount[a.bank_name] = a.current_balance; // last wins, like the Python dict-comp
    return calc.cashPositionFrom(byAccount);
  }

  /** (total_debits, total_credits) in the trailing `months` window ending `asOf`. */
  async windowTotals(asOf: string, months = 3): Promise<[number, number]> {
    const start = calc.monthsBack(asOf, months);
    const txns = await this.txns.find();
    let debits = 0;
    let credits = 0;
    for (const t of txns) {
      const d = calc.parseDate(t.txn_date);
      if (d === null || d <= start || d > asOf) continue;
      debits += t.debit;
      credits += t.credit;
    }
    return [debits, credits];
  }

  async burnAttribution(asOf: string, months = 3) {
    const start = calc.monthsBack(asOf, months);
    const txns = await this.txns.find();
    const byCategory: Record<string, number> = {};
    let total = 0;
    for (const t of txns) {
      const d = calc.parseDate(t.txn_date);
      if (d === null || d <= start || d > asOf || t.debit <= 0) continue;
      const category = t.category || 'uncategorised';
      byCategory[category] = (byCategory[category] ?? 0) + t.debit;
      total += t.debit;
    }
    const sorted = Object.fromEntries(Object.entries(byCategory).sort((a, b) => b[1] - a[1]));
    return { as_of: asOf, window_months: months, total_debits_paise: total, by_category: sorted };
  }

  async treasuryPolicy(asOf: string, bufferMonths = 6) {
    const m = await this.metrics(asOf);
    return calc.sweepSuggestion(m.cash_paise, m.net_burn_paise, bufferMonths);
  }

  async metrics(asOf: string, months = 3) {
    const cash = await this.cashPosition();
    const [debits, credits] = await this.windowTotals(asOf, months);
    return { as_of: asOf, ...calc.metricsFrom(cash, debits, credits, months) };
  }

  // ---- Mahsa contract ------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const m = await this.metrics(anchor);
    return {
      as_of: m.as_of,
      cash: m.cash_paise,
      monthly_burn: m.monthly_burn_paise,
      monthly_revenue: m.monthly_revenue_paise,
      bank_account_count: m.account_count,
      largest_account_share: m.largest_account_share,
    };
  }
}

/** Minimal RFC-4180 CSV reader (quotes + escaped quotes), matching Python's csv.reader defaults. */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else inQuotes = false;
      } else field += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
    } else field += ch;
  }
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}
