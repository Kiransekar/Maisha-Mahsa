/**
 * The Tax-Optimization Playbook catalog — the CFO's toolkit (procedural memory).
 *
 * Each playbook is a *strategy*, not a number. `applies_when` decides relevance from the org's real
 * FACTS; `evaluate` returns a DETERMINISTIC rupee impact computed here (same trust level as the
 * domain calc engines) — or `null` with a `needs` list when the inputs aren't available yet. It
 * never fabricates a figure (the Golden Rule). Every playbook carries a statute + section: no CFO
 * advice without a citation.
 *
 * Money is integer paise throughout. `_00` suffix = rupees→paise on a literal.
 */

export type FactVal = number | string | boolean;

export interface OptContext {
  facts: Record<string, FactVal>;
  org: { sector: string | null; msme: boolean; dpiit: boolean; hasGstin: boolean; hasEmployees: boolean; isCompany: boolean };
  appetite: 'low' | 'medium' | 'aggressive';
}

export interface Move {
  savingPaise: number | null; // deterministic ₹ impact, or null when inputs are missing
  needs: string[]; // FACTS/inputs required to quantify (honesty, not a fudge)
  note: string;
}

export interface Playbook {
  id: string;
  name: string;
  trigger: string; // the one-line index entry (progressive disclosure)
  category: 'direct' | 'gst' | 'structural';
  statute: string;
  section: string;
  risk: 'low' | 'medium' | 'aggressive';
  appliesWhen(ctx: OptContext): boolean;
  evaluate(ctx: OptContext): Move;
  steps: string[]; // the body, loaded on demand
}

const num = (ctx: OptContext, key: string): number | null => {
  const v = ctx.facts[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
};
const applicable = (note: string, needs: string[]): Move => ({ savingPaise: null, needs, note });

export const PLAYBOOKS: Playbook[] = [
  {
    id: 'GST-LATEFEE',
    name: 'File overdue GSTR-3B now to stop late fee + interest',
    trigger: 'GSTR-3B is filed/paid after the due date',
    category: 'gst',
    statute: 'CGST Act 2017',
    section: 'Sec 47 / Sec 50',
    risk: 'low',
    appliesWhen: (c) => c.org.hasGstin && (num(c, 'gstr3b_days_late') ?? 0) > 0,
    evaluate: (c) => {
      const days = num(c, 'gstr3b_days_late') ?? 0;
      // ₹50/day late fee (₹25 CGST + ₹25 SGST) for a non-nil return — a cost that grows daily.
      const lateFeePaise = days * 50_00;
      return { savingPaise: lateFeePaise, needs: [], note: `${days} days late — ₹50/day late fee is accruing (plus 18% p.a. interest on tax). Filing today caps it.` };
    },
    steps: ['File the pending GSTR-3B immediately.', 'Pay tax + accrued late fee + interest u/s 50 (18% p.a.).', 'Set a recurring reminder before the 20th of each month.'],
  },
  {
    id: 'MSME-43BH',
    name: 'Clear MSME dues within 45 days to avoid disallowance',
    trigger: 'A registered-MSME vendor is unpaid beyond 45 days',
    category: 'structural',
    statute: 'Income Tax Act 1961 / MSMED Act 2006',
    section: 'Sec 43B(h) / Sec 15',
    risk: 'low',
    appliesWhen: (c) => (num(c, 'msme_max_days_unpaid') ?? 0) > 45,
    evaluate: (c) => {
      const unpaid = num(c, 'msme_unpaid_paise');
      if (unpaid == null) return applicable('MSME dues beyond 45 days are DISALLOWED as a deduction until actually paid (Sec 43B(h)) — a real tax cost at year-end.', ['msme_unpaid_paise', 'marginal_rate_pct']);
      const rate = num(c, 'marginal_rate_pct') ?? 25;
      return { savingPaise: Math.round((unpaid * rate) / 100), needs: [], note: `Paying the ₹${(unpaid / 100).toFixed(0)} MSME balance before FY-end restores the deduction (else disallowed u/s 43B(h)).` };
    },
    steps: ['List MSME vendors unpaid > 45 days.', 'Pay before 31 March to keep the deduction this year.', 'Track MSME status of every vendor at onboarding.'],
  },
  {
    id: 'ADV-TAX-234C',
    name: 'Pay advance tax on schedule to avoid 234B/234C interest',
    trigger: 'Advance-tax instalments are behind the statutory schedule',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 211 / 234B / 234C',
    risk: 'low',
    appliesWhen: (c) => (num(c, 'advance_tax_q1_ratio') ?? 1) < 0.15 || (num(c, 'advance_tax_coverage') ?? 1) < 0.9,
    evaluate: (c) => applicable('Instalments are behind schedule — 1% per month interest u/s 234C accrues on each shortfall, and 234B on the annual gap.', ['estimated_annual_tax_paise', 'advance_tax_paid_paise']),
    steps: ['Estimate full-year tax liability.', 'Pay to the 15/45/75/100% cumulative schedule by 15 Jun/Sep/Dec/Mar.', 'True-up in the March instalment.'],
  },
  {
    id: 'ITC-RECON',
    name: 'Reconcile GSTR-2B and claim eligible ITC before paying cash',
    trigger: 'Claimed ITC diverges from 2B / reconciliation gap exists',
    category: 'gst',
    statute: 'CGST Rules 2017',
    section: 'Rule 36(4) / Rule 88A',
    risk: 'low',
    appliesWhen: (c) => c.org.hasGstin && ((num(c, 'reconciliation_gap') ?? 1) < 1 || (num(c, 'e_invoice_readiness') ?? 1) < 1),
    evaluate: (c) => applicable('Every ₹ of eligible ITC left unclaimed is cash paid that need not have been. Reconcile 2B and claim before the cash ledger.', ['available_2b_paise', 'itc_claimed_paise']),
    steps: ['Download GSTR-2B for the period.', 'Match against purchase register; chase missing supplier invoices.', 'Claim eligible ITC in the correct Rule 88A set-off order (IGST → CGST/SGST) before paying cash.'],
  },
  {
    id: 'REGIME-115BAA',
    name: 'Elect the 22% concessional company rate (115BAA) if it beats 30%',
    trigger: 'A company still taxed at the 30% base rate',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 115BAA',
    risk: 'medium',
    appliesWhen: (c) => c.org.isCompany,
    evaluate: (c) => applicable('115BAA fixes the company rate at 22% (effective ~25.17%) but forgoes most incentives/MAT. Compare against your incentive-heavy 30% position before electing.', ['taxable_income_paise', 'total_incentives_claimed_paise']),
    steps: ['Model tax under 30%-with-incentives vs 22%-115BAA.', 'Confirm no unabsorbed additional depreciation / MAT credit is stranded.', 'File Form 10-IC before the return due date (election is irreversible).'],
  },
  {
    id: 'ADDL-DEPR',
    name: 'Claim additional depreciation and time new-asset purchases',
    trigger: 'Manufacturing / production org acquiring plant & machinery',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 32(1)(iia)',
    risk: 'low',
    appliesWhen: (c) => /manufactur|production|industr/i.test(c.org.sector ?? ''),
    evaluate: (c) => applicable('New plant & machinery earns 20% additional depreciation. Assets bought and put to use before 3 Oct get the full year; after, only half — so timing is money.', ['new_plant_cost_paise']),
    steps: ['Identify eligible new P&M (not office/vehicles).', 'Put assets to use before 3 October for the full 20%.', 'Claim additional depreciation on top of normal depreciation.'],
  },
  {
    id: 'STARTUP-80IAC',
    name: 'Claim the 80-IAC startup tax holiday (DPIIT-recognised)',
    trigger: 'DPIIT-recognised startup with taxable profit',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 80-IAC',
    risk: 'medium',
    appliesWhen: (c) => c.org.dpiit,
    evaluate: (c) => applicable('An eligible DPIIT startup can deduct 100% of profits for any 3 consecutive years out of its first 10 — pick your most profitable years.', ['eligible_profit_paise']),
    steps: ['Obtain the inter-ministerial-board 80-IAC certificate.', 'Choose the 3 highest-profit years within the first 10.', 'Maintain the eligibility conditions (turnover, incorporation date, non-split origin).'],
  },
  {
    id: 'PRESUMPTIVE-44AD',
    name: 'Use presumptive taxation (44AD / 44ADA) if eligible',
    trigger: 'Small business / professional under the turnover limit',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 44AD / 44ADA',
    risk: 'low',
    appliesWhen: (c) => !c.org.isCompany,
    evaluate: (c) => applicable('Presumptive taxation declares income at a fixed % of receipts (8%/6% business, 50% profession), removing audit and books burden below the turnover limit.', ['gross_receipts_paise']),
    steps: ['Confirm turnover under the 44AD/44ADA limit.', 'Declare income at the presumptive rate (6% for digital receipts).', 'Avoid opting out for 5 years once opted in.'],
  },
  {
    id: 'EXPORT-LUT',
    name: 'File a LUT to export zero-rated without blocking capital in IGST',
    trigger: 'Exporter paying IGST then claiming refund',
    category: 'gst',
    statute: 'CGST Act 2017',
    section: 'Sec 16 IGST / Rule 96A',
    risk: 'low',
    appliesWhen: (c) => c.org.hasGstin && /export|saas|software|it |services/i.test(c.org.sector ?? ''),
    evaluate: (c) => applicable('Filing a Letter of Undertaking lets you export without paying IGST up front, freeing the working capital that would otherwise sit in a refund queue.', ['export_turnover_paise']),
    steps: ['File LUT (Form RFD-11) at the start of the financial year.', 'Export under LUT without charging IGST.', 'Renew the LUT every financial year.'],
  },
  {
    id: 'RND-35-2AB',
    name: 'Claim weighted R&D deduction on in-house research',
    trigger: 'Tech / pharma org with in-house R&D spend',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 35 / 35(2AB)',
    risk: 'medium',
    appliesWhen: (c) => /pharma|tech|software|biotech|deep|hardware|r&d|research/i.test(c.org.sector ?? ''),
    evaluate: (c) => applicable('In-house R&D on an approved facility earns a deduction on revenue + capital research spend — quantify from the R&D cost centre.', ['rd_expense_paise']),
    steps: ['Get DSIR approval for the R&D facility (Form 3CK).', 'Ring-fence R&D revenue and capital spend in the ledger.', 'File Form 3CLA with the audit report.'],
  },
  {
    id: 'DIR-REMUN',
    name: 'Balance director remuneration between salary and dividend',
    trigger: 'Owner-managed company paying directors',
    category: 'direct',
    statute: 'Income Tax Act 1961 / Companies Act 2013',
    section: 'Sec 15 / Sec 197',
    risk: 'medium',
    appliesWhen: (c) => c.org.isCompany && c.org.hasEmployees,
    evaluate: (c) => applicable('Salary is deductible for the company but taxed in the director’s slab; dividend is not deductible but may be taxed lower. The mix minimises the combined entity+individual tax.', ['director_remuneration_paise', 'company_rate_pct', 'director_slab_pct']),
    steps: ['Compute combined tax under salary-heavy vs dividend-heavy mixes.', 'Respect Companies Act limits on managerial remuneration.', 'Keep board resolutions for the chosen structure.'],
  },
  {
    id: 'TDS-197',
    name: 'Apply for a lower/nil TDS certificate on receivables (197)',
    trigger: 'Receipts suffering TDS above the actual tax liability',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 197',
    risk: 'low',
    appliesWhen: (c) => (num(c, 'tds_days_overdue') ?? 0) >= 0 && ((num(c, 'advance_tax_coverage') ?? 1) < 1 || !c.org.isCompany),
    evaluate: (c) => applicable('If TDS deducted on your receipts exceeds your real liability, a Sec 197 certificate lowers the deduction and stops locking cash in refunds.', ['receipts_subject_to_tds_paise', 'estimated_annual_tax_paise']),
    steps: ['File Form 13 with projected income and tax.', 'Share the 197 certificate with customers/deductors.', 'Renew each financial year.'],
  },
  {
    id: 'DEDUCTIONS-80C-80D',
    name: 'Maximise employee 80C / 80D / 80CCD(1B) declarations',
    trigger: 'Org runs payroll with employees on the old regime',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 80C / 80D / 80CCD(1B)',
    risk: 'low',
    appliesWhen: (c) => c.org.hasEmployees,
    evaluate: (c) => applicable('Old-regime employees can cut taxable income via 80C (₹1.5L), 80D health cover, and the extra ₹50k NPS 80CCD(1B) — collect proofs before payroll finalises TDS.', ['employees_old_regime_count', 'avg_unused_80c_paise']),
    steps: ['Run an investment-declaration drive before year-end TDS.', 'Nudge under-utilised 80C/80CCD(1B) headroom.', 'Reconcile declared vs actual proofs in Q4.'],
  },
  {
    id: 'CF-LOSS-SETOFF',
    name: 'Set off and carry forward losses in the optimal order',
    trigger: 'Org with brought-forward losses or unabsorbed depreciation',
    category: 'direct',
    statute: 'Income Tax Act 1961',
    section: 'Sec 72 / 32(2)',
    risk: 'low',
    appliesWhen: (c) => (num(c, 'mat_exposure') ?? 0) > 0 || !c.org.isCompany,
    evaluate: (c) => applicable('Business losses expire after 8 years but unabsorbed depreciation never does — set off expiring losses first to avoid forfeiting them.', ['brought_forward_loss_paise', 'unabsorbed_depreciation_paise', 'current_profit_paise']),
    steps: ['Age the brought-forward losses.', 'Set off the earliest-expiring business losses first.', 'Preserve unabsorbed depreciation (no expiry) for later.'],
  },
];
