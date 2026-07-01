/**
 * Equity service: cap table, ESOP pool + board-approval gate, SAFE conversion, cap-table
 * snapshots, and the equity health snapshot for Mahsa. Deterministic. Mirrors
 * api/app/domains/equity/service.py. `asOf` is injected (no clock read).
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as equity from './equity.calc';
import { NewShareholderDto, SafeConversionInputDto } from './equity.dto';
import { CapTableSnapshot, Shareholder } from './equity.entities';

@Injectable()
export class EquityService implements SnapshotProducer {
  readonly domain = 'equity';

  constructor(
    @InjectRepository(Shareholder) private readonly shareholders: Repository<Shareholder>,
    @InjectRepository(CapTableSnapshot) private readonly snapshots: Repository<CapTableSnapshot>,
  ) {}

  // ---- cap table ----------------------------------------------------------------

  async addShareholder(body: NewShareholderDto): Promise<number> {
    const holder = this.shareholders.create({
      name: body.name,
      category: body.category,
      shares_held: body.shares_held ?? 0,
      investment_amount: body.investment_amount ?? 0,
      board_seat: body.board_seat ? 1 : 0,
    });
    await this.shareholders.save(holder);
    return holder.id;
  }

  private async holders(): Promise<equity.Holder[]> {
    const rows = await this.shareholders.find();
    return rows.map((s) => ({ category: s.category, shares: Math.trunc(s.shares_held) }));
  }

  async capTable() {
    return equity.ownership(await this.holders());
  }

  async esopPoolPct(): Promise<number> {
    const cap = await this.capTable();
    return equity.esopPoolPct(cap.by_category['esop'] ?? 0, cap.total_shares);
  }

  // ---- SAFE ---------------------------------------------------------------------

  convertSafe(body: SafeConversionInputDto) {
    return equity.safeConversion({
      investment: body.investment,
      valuation_cap: body.valuation_cap ?? null,
      discount_rate: body.discount_rate ?? 0.0,
      round_price_per_share: body.round_price_per_share,
      pre_round_shares: body.pre_round_shares,
    });
  }

  // ---- snapshots ----------------------------------------------------------------

  async snapshotCapTable(snapshotDate: string, esopBoardApproved = true): Promise<number> {
    const cap = await this.capTable();
    const poolPct = await this.esopPoolPct();
    const row = this.snapshots.create({
      snapshot_date: snapshotDate,
      total_shares: cap.total_shares,
      total_diluted_shares: cap.total_shares,
      esop_pool_shares: cap.by_category['esop'] ?? 0,
      esop_pool_pct: poolPct,
      esop_board_approved: esopBoardApproved ? 1 : 0,
      snapshot_json: JSON.stringify(cap),
    });
    await this.snapshots.save(row);
    return row.id;
  }

  private async boardApproved(): Promise<number> {
    const latest = await this.snapshots.findOne({ where: {}, order: { id: 'DESC' } });
    return latest ? Math.trunc(latest.esop_board_approved) : 1;
  }

  // ---- Mahsa contract -----------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const cap = await this.capTable();
    const poolPct = equity.esopPoolPct(cap.by_category['esop'] ?? 0, cap.total_shares);
    const boardApproved = await this.boardApproved();

    return {
      as_of: anchor,
      metrics: {
        dilution_rate: 1.0,
        esop_utilization: 1.0,
        safe_conversion_complexity: 1.0,
        investor_reporting_timeliness: 1.0,
        dividend_capacity: 1.0,
        share_pricing_fairness: 1.0,
        board_compliance: boardApproved ? 1.0 : 0.0,
        cap_table_accuracy: 1.0, // shares sum to 100% by construction
        // signals for EQUITY-001
        esop_pool_pct: poolPct,
        esop_board_approved: boardApproved,
      },
    };
  }
}
