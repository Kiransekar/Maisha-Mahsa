/**
 * Ledger service: chart of accounts, balanced journal posting, financial statements,
 * depreciation, and the ledger health snapshot for Mahsa. Exact paise; deterministic.
 * Mirrors api/app/domains/ledger/service.py.
 *
 * Ledger has no Mahsa sub-vector; Mahsa enforces LEDGER-001 (trial balance must tie out)
 * on the snapshot's trial_balance_diff.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as ledger from './ledger.calc';
import { NewAccountDto, NewJournalEntryDto } from './ledger.dto';
import { ChartOfAccounts, FixedAsset, JournalEntry, JournalLine } from './ledger.entities';

const VALID_TYPES = [...ledger.DEBIT_NATURED, ...ledger.CREDIT_NATURED] as readonly string[];

@Injectable()
export class LedgerService implements SnapshotProducer {
  readonly domain = 'ledger';

  constructor(
    @InjectRepository(ChartOfAccounts) private readonly accounts: Repository<ChartOfAccounts>,
    @InjectRepository(JournalEntry) private readonly entries: Repository<JournalEntry>,
    @InjectRepository(JournalLine) private readonly lines: Repository<JournalLine>,
    @InjectRepository(FixedAsset) private readonly assets: Repository<FixedAsset>,
  ) {}

  // ---- chart of accounts ----------------------------------------------------------

  async createAccount(body: NewAccountDto): Promise<number> {
    if (!VALID_TYPES.includes(body.account_type)) {
      throw new Error(`invalid account_type: ${body.account_type}`);
    }
    const acct = this.accounts.create({
      code: body.code,
      name: body.name,
      account_type: body.account_type,
      sub_type: body.sub_type ?? null,
      opening_balance: body.opening_balance ?? 0,
      is_cash_account: 0,
      is_bank_account: 0,
    });
    await this.accounts.save(acct);
    return acct.id;
  }

  /**
   * Post a system-generated entry from another module (payroll/gst/revenue). Tags the entry
   * with its source (which flags is_auto_generated); use ledger.calc's payrollJournal /
   * salesJournal / gstPaymentJournal to build the lines.
   */
  async autoPost(args: {
    source: string;
    entry_date: string;
    description: string;
    lines: ledger.JournalLineOut[];
    reference?: string | null;
  }) {
    if (args.source === 'manual') {
      throw new Error('auto_post requires a non-manual source (e.g. payroll/gst/revenue)');
    }
    return this.postJournalEntry({
      entry_date: args.entry_date,
      description: args.description,
      lines: args.lines,
      source: args.source,
      reference: args.reference,
    });
  }

  // ---- journal --------------------------------------------------------------------

  /**
   * Post a balanced journal entry. Refuses (throws) an unbalanced entry — this is the first
   * line of defence; Mahsa's LEDGER-001 is the backstop on aggregate state.
   */
  async postJournalEntry(args: {
    entry_date: string;
    description: string;
    lines: Array<{ account_id: number; debit?: number; credit?: number; description?: string | null }>;
    source?: string;
    reference?: string | null;
  }) {
    const source = args.source ?? 'manual';
    if (args.lines.length < 2) {
      throw new Error('a journal entry needs at least two lines');
    }
    if (!ledger.isBalanced(args.lines)) {
      throw new Error('journal entry is not balanced (total debits != total credits)');
    }

    const totalDebit = args.lines.reduce((s, ln) => s + ~~(ln.debit ?? 0), 0);
    const totalCredit = args.lines.reduce((s, ln) => s + ~~(ln.credit ?? 0), 0);
    const entry = this.entries.create({
      entry_date: args.entry_date,
      description: args.description,
      reference: args.reference ?? null,
      source,
      total_debit: totalDebit,
      total_credit: totalCredit,
      is_auto_generated: source === 'manual' ? 0 : 1,
    });
    await this.entries.save(entry);
    for (const ln of args.lines) {
      await this.lines.save(
        this.lines.create({
          journal_entry_id: entry.id,
          account_id: ~~ln.account_id,
          debit: ~~(ln.debit ?? 0),
          credit: ~~(ln.credit ?? 0),
          description: ln.description ?? null,
        }),
      );
    }
    return {
      journal_entry_id: entry.id,
      total_debit: totalDebit,
      total_credit: totalCredit,
    };
  }

  // ---- statements -----------------------------------------------------------------

  private async typedLines(): Promise<ledger.TypedRow[]> {
    const accts = await this.accounts.find();
    const types = new Map(accts.map((a) => [a.id, a.account_type]));
    const lines = await this.lines.find();
    return lines.map((ln) => ({
      account_type: types.get(ln.account_id) ?? 'asset',
      debit: ~~ln.debit,
      credit: ~~ln.credit,
    }));
  }

  async trialBalance() {
    const rows = await this.typedLines();
    return ledger.trialBalance(rows.map((r) => ({ debit: r.debit, credit: r.credit })));
  }

  async profitAndLoss() {
    return ledger.profitAndLoss(await this.typedLines());
  }

  async balanceSheet() {
    return ledger.balanceSheet(await this.typedLines());
  }

  /**
   * Account-wise general ledger: every posting to the account in date order with a running
   * balance (opening + cumulative debit − credit).
   */
  async generalLedger(accountId: number) {
    const acct = await this.accounts.findOne({ where: { id: accountId } });
    if (acct === null) throw new Error(`account ${accountId} not found`);
    const rows = await this.lines.find({ where: { account_id: accountId } });
    const entries = await this.entries.find();
    const dateById = new Map(entries.map((e) => [e.id, e.entry_date]));
    const enriched = rows
      .map((jl) => ({ jl, entry_date: dateById.get(jl.journal_entry_id) ?? '' }))
      .sort((a, b) =>
        a.entry_date < b.entry_date ? -1 : a.entry_date > b.entry_date ? 1 : a.jl.id - b.jl.id,
      );
    let balance = ~~acct.opening_balance;
    const lines = enriched.map(({ jl, entry_date }) => {
      balance += ~~jl.debit - ~~jl.credit;
      return {
        date: entry_date,
        description: jl.description,
        debit: ~~jl.debit,
        credit: ~~jl.credit,
        balance,
      };
    });
    return {
      account_id: accountId,
      code: acct.code,
      name: acct.name,
      opening_balance: ~~acct.opening_balance,
      lines,
      closing_balance: balance,
    };
  }

  /**
   * Direct-method cash-flow statement. Each entry's net cash movement is classified by its
   * non-cash counterpart: income/expense → operating, asset → investing, equity/liability →
   * financing. Requires cash/bank accounts to be flagged.
   */
  async cashFlow() {
    const accts = await this.accounts.find();
    const byId = new Map(accts.map((a) => [a.id, a]));
    const cashIds = new Set(
      accts.filter((a) => a.is_cash_account || a.is_bank_account).map((a) => a.id),
    );
    const flows: Record<string, number> = { operating: 0, investing: 0, financing: 0, net_change: 0 };
    if (cashIds.size === 0) return flows;
    const bucketOf: Record<string, string> = {
      income: 'operating',
      expense: 'operating',
      asset: 'investing',
      liability: 'financing',
      equity: 'financing',
    };
    const allEntries = await this.entries.find();
    for (const entry of allEntries) {
      const lines = await this.lines.find({ where: { journal_entry_id: entry.id } });
      const cashDelta = lines
        .filter((l) => cashIds.has(l.account_id))
        .reduce((s, l) => s + ~~l.debit - ~~l.credit, 0);
      const nonCash = lines.filter((l) => !cashIds.has(l.account_id));
      if (cashDelta === 0 || nonCash.length === 0) continue;
      const counterpart = nonCash.reduce((best, l) =>
        ~~l.debit + ~~l.credit > ~~best.debit + ~~best.credit ? l : best,
      );
      const type = byId.get(counterpart.account_id)?.account_type ?? 'operating';
      const bucket = bucketOf[type] ?? 'operating';
      flows[bucket] += cashDelta;
    }
    flows.net_change = flows.operating + flows.investing + flows.financing;
    return flows;
  }

  // ---- depreciation ---------------------------------------------------------------

  async annualDepreciation(assetId: number): Promise<number> {
    const asset = await this.assets.findOne({ where: { id: assetId } });
    if (asset === null) throw new Error(`fixed asset ${assetId} not found`);
    if (asset.depreciation_method === 'slm') {
      return ledger.slmAnnual(asset.purchase_cost, asset.salvage_value, asset.useful_life_years);
    }
    return ledger.wdvAnnual(asset.wdv, asset.depreciation_rate);
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const tb = await this.trialBalance();
    const pnl = await this.profitAndLoss();
    return {
      as_of: anchor,
      metrics: {
        // consumed by LEDGER-001 (must be 0)
        trial_balance_diff_paise: tb.diff,
        net_profit_paise: pnl.net_profit,
      },
    };
  }
}
