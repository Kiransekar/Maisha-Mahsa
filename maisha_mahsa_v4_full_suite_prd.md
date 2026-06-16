# Project Maisha-Mahsa v4.0 PRD
## The Complete Startup Financial Suite | Indian Regulatory Context | Rust DIF Core

**Version:** 4.0.0 — The Full Suite Release  
**Status:** Build-ready  
**Scope:** Every financial function an Indian startup needs, from incorporation to Series A  
**Philosophy:** Single user. Single approval. ~Rs.800/mo infra (up from Rs.500 for full-suite storage/compute). 100% open source. No paid APIs. English-only. You own the entire stack.

---

## 0. What Changed from v3.0

v3.0 gave us the Rust sidecar and email channel. v4.0 expands the scope to cover the full financial lifecycle of an Indian startup.

| | v3.0 | v4.0 |
|---|---|---|
| **Scope** | Virtual CFO + daily brief + approvals | **Complete financial suite** — banking, accounting, payroll, GST, TDS, tax, invoicing, cap table, investor reporting, audit readiness |
| **Modules** | Core (Maisha + Mahsa + Mail) | **12 domain modules** — each with its own Rust validator + Python service |
| **Intent IR** | Single 8-dim vector | **Hierarchical IR** — global 8-dim + per-domain sub-vectors (payroll, tax, treasury) |
| **Database** | Single SQLite file | **SQLite with domain schemas** — 40+ tables, still single-file, still Git-friendly |
| **Build time** | 8 weekends | **16 weekends** — still solo, still buildable |
| **Monthly cost** | Rs.0-500 | **Rs.600-800** — extra storage for document vault + optional Hetzner VPS |

The core architecture (Maisha <-> Mahsa over HTTP, email channel, deterministic validation) is unchanged. What changes is the surface area — we now model the entire startup finance stack.

---

## 1. The Complete Feature Matrix

### 1.1 Banking & Treasury (Module: treasury)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Multi-bank aggregation | HDFC, ICICI, Axis, SBI — CSV/MT940/PSD2 (when available) import | Reconciliation against ledger |
| Cash position | Real-time consolidated cash across all accounts | Liquidity ratio check |
| Runway calculator | Burn x cash = months remaining | RED if < 3 months |
| Burn attribution | Categorize burn by team/vendor/function | Variance vs budget |
| Treasury policy | Auto-sweep rules, FD laddering, liquid fund suggestions | Intent alignment |
| UPI reconciliation | Match UPI refs to invoices/payables | Duplicate detection |
| Bank guarantee tracking | BG expiry alerts, margin money tracking | Compliance calendar |

### 1.2 Invoicing & Receivables (Module: revenue)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Invoice generation | GST-compliant invoices (IRN-ready for e-invoicing) | GSTIN validation, HSN code check |
| AR aging | 0-30, 31-60, 61-90, 90+ buckets | Concentration risk flag |
| Dunning engine | Automated reminder emails (T-7, T-3, T-1, T+1, T+7) | Tone calibration via Intent |
| Credit notes | Post-invoice adjustments, GST impact | Rule: credit note within 6 months |
| Revenue recognition | Monthly recognized revenue (accrual basis) | Deferred revenue tracking |
| Customer master | PAN, GSTIN, TDS applicability, payment terms | TDS rate auto-determination |
| Export invoicing | LUT bond tracking, IGST refund, FEMA compliance | FEMA Section 10 validation |

### 1.3 Payables & Vendor Management (Module: payables)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Vendor onboarding | PAN, GSTIN, bank details, MSME status | MSME payment due-date rules (45 days) |
| Purchase order workflow | PO -> GRN -> Invoice 3-way match | Variance tolerance (+/-5%) |
| AP aging | Due date tracking, early payment discount capture | Cash flow impact before approval |
| TDS on payments | 194C (contractors), 194J (professionals), 194H, 194I | Auto-calculation, threshold checks |
| MSME compliance | Auto-flag vendors with MSME registration | Payment within 45 days (MSMED Act) |
| Recurring payables | AWS, GitHub, SaaS subscriptions — auto-categorize | Budget vs actual |

### 1.4 Payroll & Statutory Compliance (Module: payroll)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Salary structure | CTC breakdown: Basic, HRA, LTA, PF, ESI, NPS, TDS | PF wage ceiling (Rs.15,000), ESI ceiling (Rs.21,000) |
| Monthly payroll run | Net pay computation, TDS deduction, arrears | TDS Section 192 slab validation |
| PF (EPFO) | ECR generation, UAN mapping, monthly upload | PF Act Section 6 compliance |
| ESI | IP/ESI contribution, monthly return | ESI Act Section 39-40 |
| PT (Professional Tax) | State-wise slabs (MH, KA, TN, etc.), monthly payment | State-specific rules |
| LWF (Labour Welfare Fund) | Applicable states, periodic contribution | State-specific calendars |
| Form 16 / 16A | Annual TDS certificate generation | 31 May deadline |
| Leave & attendance integration | Optional: connect to HR tool or manual entry | Leave encashment tax treatment |
| Gratuity provision | Actuarial provision, eligibility tracking (5 years) | Payment of Gratuity Act |
| Bonus provision | Statutory bonus (Rs.21,000 wage ceiling, 8.33% min) | Payment of Bonus Act |

### 1.5 GST Compliance (Module: gst)

| Feature | Description | Mahsa Validation |
|---|---|---|
| GSTR-1 (Outward supplies) | B2B, B2C, HSN summary, JSON generation | Invoice-level validation |
| GSTR-2B (Inward supplies) | Auto-reconcile with books, ITC claim eligibility | Rule 36(4) 5% cap, blocked credits |
| GSTR-3B | Monthly summary return, tax payment challan | Late filing penalty calc |
| GSTR-9 (Annual) | Consolidated annual return | Reconciliation with audited books |
| GSTR-9C (Reconciliation) | CA-certified reconciliation statement | Turnover > Rs.5Cr trigger |
| e-Invoicing | IRN generation via GST portal (turnover > Rs.5Cr) | QR code, signed invoice |
| HSN master | 4/6/8-digit codes, GST rate mapping | Rate change alerts |
| Reverse charge mechanism | RCM tracking, self-invoice for unregistered vendors | ITC availability rules |
| Composition scheme | Eligibility check, quarterly filing (if opted) | Turnover threshold monitoring |
| LUT for exports | Letter of Undertaking, annual renewal | FEMA + GST cross-check |

### 1.6 Income Tax & TDS (Module: tax)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Advance tax | Quarterly estimates (15 Jun, 15 Sep, 15 Dec, 15 Mar) | 234B/234C interest calc |
| TDS return (24Q, 26Q, 27Q) | Quarterly filing, challan reconciliation | Late filing fees (Rs.200/day) |
| TDS rate engine | Section-wise rates + thresholds + surcharge + cess | Dynamic rate lookup |
| Form 26AS reconciliation | Annual tax credit statement matching | Mismatch alerts |
| ITR filing (Company/LLP) | ITR-5/ITR-6 preparation, tax computation | Due date: 31 Oct (audit) / 31 Jul (non-audit) |
| Tax audit (44AB) | Trigger: turnover > Rs.1Cr / Rs.10Cr (digital) | CA appointment tracking |
| Transfer pricing | Basic documentation (if international transactions) | Threshold: Rs.1Cr aggregate |
| MAT (Minimum Alternate Tax) | 15% book profit + surcharge + cess | AMT for LLPs |
| Tax holiday (Section 80IAC) | Startup India recognition, 3-year holiday tracking | Eligibility: DPIIT recognition |

### 1.7 Accounting & Bookkeeping (Module: ledger)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Chart of accounts | Indian GAAP-compliant COA (SME format) | Account code uniqueness |
| Journal entries | Manual + auto-generated (payroll, GST, depreciation) | Double-entry validation |
| General ledger | Account-wise transaction history | Balance check |
| Trial balance | Monthly TB with grouping | Dr/Cr balance validation |
| P&L statement | Monthly/quarterly/annual | Revenue vs expense classification |
| Balance sheet | Assets, liabilities, equity | Accounting equation check |
| Cash flow statement | Direct + indirect method | Reconciliation with bank |
| Bank reconciliation | Auto-match + manual exception handling | Unexplained variance flag |
| Fixed asset register | Depreciation (SLM/WDV), asset disposal | Companies Act Schedule II rates |
| Prepaid & accruals | Auto-amortization, monthly true-up | Balance sheet integrity |
| Inter-branch transfers | Cost center allocation, transfer pricing | Arm's length documentation |

### 1.8 Budgeting & Forecasting (Module: forecast)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Annual budget | Team-wise, function-wise, vendor-wise budgets | Variance analysis |
| Rolling forecast | 12-month forward, re-forecast quarterly | Confidence interval |
| Scenario modeling | Base, optimistic, pessimistic cases | Sensitivity tables |
| Headcount planning | CTC x headcount = payroll forecast | Ramp schedule validation |
| Cash flow forecast | Weekly cash position projection | Overdraft alert |
| Unit economics | CAC, LTV, payback period, gross margin | Benchmark comparison |
| Burn multiple | Net burn / net new ARR | Investor metric |
| Revenue recognition forecast | Contract-to-revenue timing | SaaS metric compliance |

### 1.9 Cap Table & Equity (Module: equity)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Cap table management | Founder, ESOP, investor, advisor stakes | Total = 100% validation |
| ESOP pool | Grant, vesting (4-year cliff), exercise tracking | SEBI SBEB Regulations |
| SAFE notes | Valuation cap, discount rate, pro-rata tracking | Conversion waterfall |
| Convertible notes | Interest accrual, conversion triggers | Termsheet validation |
| Investor reporting | Quarterly updates, KPI dashboards, financials | Consistency with ledger |
| Dividend distribution | Board resolution, DDT (if applicable), payment | Companies Act Section 123 |
| Share certificate tracking | Physical + demat, transfer forms | Stamp duty calc |
| Rights issue / buyback | Compliance checklist, board resolutions | SEBI + Companies Act |

### 1.10 Compliance & Audit (Module: compliance)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Compliance calendar | ROC, GST, TDS, PF, ESI, PT, IT — all deadlines | T-7, T-1, T-0 email alerts |
| MCA filings | AOC-4, MGT-7, DIR-3 KYC, DPT-3 | Due date tracking |
| Secretarial compliance | Board minutes, AGM notices, resolutions | Companies Act Section 118 |
| Statutory audit support | TB, ledgers, schedules, confirmations | Auditor query response |
| Internal audit | Monthly control testing, exception reports | Risk-weighted scoring |
| RBI compliance (if NBFC/Fintech) | Returns, capital adequacy, exposure norms | Regulatory threshold alerts |
| DPIIT reporting | Startup India periodic reporting | Recognition validity |
| Document vault | Digitized contracts, invoices, challans, returns | 7-year retention, hash-chained |

### 1.11 Expense Management (Module: expense)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Expense capture | Photo -> OCR (Tesseract) -> structured data | GSTIN extraction, amount validation |
| Reimbursement workflow | Employee claim -> manager approval (you) -> payment | Policy limit check |
| Petty cash | Float management, imprest system | Threshold: Rs.10,000 |
| Corporate card reconciliation | Statement import, transaction matching | Personal expense flag |
| Mileage & travel | Local conveyance, outstation travel, per diem | Policy compliance |
| Expense analytics | Category-wise spend, trend analysis | Budget burn rate |

### 1.12 Document Management (Module: vault)

| Feature | Description | Mahsa Validation |
|---|---|---|
| Ingestion pipeline | Scan -> OCR -> classify -> tag -> store | Duplicate detection |
| Document types | Invoice, PO, GRN, challan, contract, return, certificate | Auto-classification |
| Full-text search | OCR text + metadata + tags | Indexed search |
| Retention policy | 7 years statutory, 3 years operational, permanent for equity | Auto-archive rules |
| Audit trail | Who uploaded, when, hash, version | Immutable log |
| Access control | Single user now, RBAC scaffold for future | Permission matrix |

---

## 2. The Expanded Architecture (v4.0)

### 2.1 System Diagram

                                    YOU (Founder)
                                       |
           +---------------------------+---------------------------+
           |                           |                           |
           v                           v                           v
    +-------------+            +-------------+            +-------------+
    |   Daily     |            |   Weekly    |            |  Approval   |
    |   Email     |            |   Review    |            |   Queue     |
    |  (8pm)      |            |  (15 min)   |            |   (Email)   |
    +------+------+            +------+------+            +------+------+
           |                           |                           |
           +---------------------------+---------------------------+
                                       |
                                       v
                        +-----------------------------+
                        |     MAISHA (Python)         |
                        |  - LLM orchestrator         |
                        |  - 12 domain services       |
                        |  - Web UI (FastAPI+HTMX)    |
                        +--------------+--------------+
                                       | HTTP POST /fold
                                       | { domain, query, draft, snapshot,
                                       |   rules_version, user_profile }
                                       v
                        +-----------------------------+
                        |     MAHSA (Rust sidecar)    |
                        |  - Domain router              |
                        |  - Global 8-dim fold         |
                        |  - Per-domain sub-folds      |
                        |  - 18 CA-signed rules        |
                        |  - Hierarchical validator    |
                        |  - ~50-100 micros per call    |
                        |  - 12 MB static binary       |
                        +--------------+--------------+
                                       | JSON
                                       v
                        +-----------------------------+
                        |     MAIL CHANNEL            |
                        |  - Daily 8pm digest          |
                        |  - Per-approval emails       |
                        |  - Compliance alerts         |
                        |  - Exception reports         |
                        +-----------------------------+

### 2.2 The Hierarchical Intent IR

v3.0 had a single 8-dim vector. v4.0 introduces a hierarchical IR — one global vector + domain-specific sub-vectors.

#### Global Intent (8-dim) — unchanged

Same 8 dimensions as v3.0: cash_flow, risk_exposure, liquidity, tax_efficiency, compliance, diversification, currency_hedge, growth.

#### Domain Sub-Vectors (computed on demand)

Each domain module can compute a specialized sub-vector when the query touches that domain:

| Domain | Sub-Vector Dimensions | Description |
|---|---|---|
| payroll | pf_compliance, esi_compliance, tds_accuracy, pt_state, lwf_state, gratuity_reserve, bonus_reserve, leave_liability | Statutory payroll health |
| gst | filing_timeliness, itc_optimization, e_invoice_readiness, hsn_accuracy, rcm_compliance, lut_validity, reconciliation_gap, penalty_exposure | GST operational health |
| tax | advance_tax_coverage, tds_deposit_timeliness, 26as_match, audit_trigger, mat_exposure, holiday_utilization, tp_documentation, itr_accuracy | Direct tax health |
| treasury | runway_months, burn_stability, cash_concentration, fd_exposure, forex_exposure, credit_line_utilization, sweep_efficiency, liquidity_stress | Treasury health |
| revenue | ar_turnover, dunning_effectiveness, credit_risk, revenue_quality, deferred_revenue, export_ratio, irn_coverage, customer_concentration | Revenue health |
| payables | ap_turnover, msme_compliance, tds_deposit_status, po_coverage, early_pay_discount_capture, vendor_concentration, recurring_spend, dispute_rate | Payables health |
| equity | dilution_rate, esop_utilization, safe_conversion_complexity, investor_reporting_timeliness, dividend_capacity, share_pricing_fairness, board_compliance, cap_table_accuracy | Equity health |
| compliance | roc_filing_status, gst_filing_status, tds_filing_status, pf_filing_status, esi_filing_status, pt_filing_status, secretarial_score, audit_readiness | Overall compliance score |

How it works:
- Every query triggers the global 8-dim fold
- If the query classifier detects a domain (e.g., "What is my GST liability?"), Mahsa also computes the gst sub-vector
- The sub-vector is returned in the fold result and drives domain-specific UI/email rendering
- The global vector still governs the overall approval mode (Green/Yellow/Red)

---

## 3. The Data Model (SQLite, 40+ tables)

The database remains a single SQLite file. It is structured into 12 domain schemas plus shared tables.

### 3.1 Shared Tables

CREATE TABLE company (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    cin TEXT UNIQUE,
    pan TEXT UNIQUE NOT NULL,
    gstin TEXT UNIQUE,
    incorporation_date TEXT,
    financial_year_end TEXT DEFAULT '03-31',
    msme_registration TEXT,
    dpiit_recognition TEXT,
    sector TEXT,
    address TEXT,
    state TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'founder',
    expertise TEXT DEFAULT 'founder',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    domain TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT,
    intent_global TEXT,
    intent_domain TEXT,
    validation_status TEXT,
    rules_version TEXT NOT NULL,
    prev_hash TEXT,
    this_hash TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    domain TEXT,
    entity_id TEXT,
    ocr_text TEXT,
    upload_date TEXT DEFAULT CURRENT_TIMESTAMP,
    retention_until TEXT,
    sha256 TEXT NOT NULL,
    tags TEXT
);

CREATE TABLE compliance_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    form_name TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filing_period TEXT,
    status TEXT DEFAULT 'pending',
    filed_date TEXT,
    acknowledgement TEXT,
    penalty_amount REAL DEFAULT 0,
    reminder_sent INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rules_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    domain TEXT NOT NULL,
    rule_id TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    statute TEXT,
    section TEXT,
    condition_logic TEXT,
    severity TEXT DEFAULT 'warning',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(version, rule_id)
);

### 3.2 Treasury Domain

CREATE TABLE bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc TEXT NOT NULL,
    account_type TEXT,
    opening_balance REAL,
    current_balance REAL,
    currency TEXT DEFAULT 'INR',
    is_primary INTEGER DEFAULT 0,
    last_sync TEXT
);

CREATE TABLE bank_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    txn_date TEXT NOT NULL,
    description TEXT,
    reference TEXT,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    balance REAL,
    category TEXT,
    matched_invoice_id INTEGER,
    matched_vendor_id INTEGER,
    is_reconciled INTEGER DEFAULT 0,
    FOREIGN KEY (account_id) REFERENCES bank_accounts(id)
);

CREATE TABLE fixed_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER,
    fd_number TEXT NOT NULL,
    principal REAL NOT NULL,
    interest_rate REAL NOT NULL,
    start_date TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    maturity_amount REAL,
    tds_deducted REAL DEFAULT 0,
    status TEXT DEFAULT 'active'
);

### 3.3 Revenue Domain

CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pan TEXT,
    gstin TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    payment_terms INTEGER DEFAULT 30,
    tds_applicable INTEGER DEFAULT 0,
    tds_section TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    invoice_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    subtotal REAL NOT NULL,
    gst_rate REAL,
    igst_amount REAL DEFAULT 0,
    cgst_amount REAL DEFAULT 0,
    sgst_amount REAL DEFAULT 0,
    total_amount REAL NOT NULL,
    tds_amount REAL DEFAULT 0,
    net_receivable REAL NOT NULL,
    irn TEXT,
    qr_code_path TEXT,
    status TEXT DEFAULT 'draft',
    paid_date TEXT,
    paid_amount REAL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    hsn_code TEXT,
    quantity REAL DEFAULT 1,
    rate REAL NOT NULL,
    amount REAL NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_note_number TEXT UNIQUE NOT NULL,
    invoice_id INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    reason TEXT,
    amount REAL NOT NULL,
    gst_adjustment REAL DEFAULT 0,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

### 3.4 Payables Domain

CREATE TABLE vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pan TEXT,
    gstin TEXT,
    msme_status INTEGER DEFAULT 0,
    msme_type TEXT,
    bank_account TEXT,
    ifsc TEXT,
    payment_terms INTEGER DEFAULT 30,
    tds_section TEXT,
    tds_threshold REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT UNIQUE NOT NULL,
    vendor_id INTEGER NOT NULL,
    po_date TEXT NOT NULL,
    delivery_date TEXT,
    total_amount REAL NOT NULL,
    status TEXT DEFAULT 'open',
    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL,
    vendor_id INTEGER NOT NULL,
    po_id INTEGER,
    bill_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    subtotal REAL NOT NULL,
    gst_amount REAL DEFAULT 0,
    tds_amount REAL DEFAULT 0,
    total_amount REAL NOT NULL,
    status TEXT DEFAULT 'open',
    paid_date TEXT,
    paid_amount REAL DEFAULT 0,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
);

### 3.5 Payroll Domain

CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    pan TEXT,
    uan TEXT,
    esi_ip_number TEXT,
    date_of_joining TEXT NOT NULL,
    date_of_exit TEXT,
    status TEXT DEFAULT 'active',
    bank_account TEXT,
    ifsc TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE salary_structures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    basic REAL NOT NULL,
    hra REAL NOT NULL,
    lta REAL DEFAULT 0,
    special_allowance REAL DEFAULT 0,
    employer_pf REAL NOT NULL,
    employer_esi REAL DEFAULT 0,
    employee_pf REAL NOT NULL,
    employee_esi REAL DEFAULT 0,
    professional_tax REAL DEFAULT 0,
    tds_monthly REAL DEFAULT 0,
    gross_salary REAL NOT NULL,
    net_salary REAL NOT NULL,
    ctc REAL NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE payroll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_year TEXT NOT NULL,
    run_date TEXT NOT NULL,
    total_gross REAL,
    total_deductions REAL,
    total_net REAL,
    total_pf_employer REAL,
    total_esi_employer REAL,
    status TEXT DEFAULT 'draft',
    ecr_generated INTEGER DEFAULT 0,
    ecr_file_path TEXT
);

CREATE TABLE payroll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payroll_run_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    gross REAL NOT NULL,
    basic REAL NOT NULL,
    hra REAL NOT NULL,
    lta REAL DEFAULT 0,
    special_allowance REAL DEFAULT 0,
    employee_pf REAL NOT NULL,
    employee_esi REAL DEFAULT 0,
    professional_tax REAL DEFAULT 0,
    tds REAL DEFAULT 0,
    other_deductions REAL DEFAULT 0,
    net_pay REAL NOT NULL,
    FOREIGN KEY (payroll_run_id) REFERENCES payroll_runs(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE esop_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    grant_date TEXT NOT NULL,
    vesting_start_date TEXT NOT NULL,
    cliff_months INTEGER DEFAULT 12,
    vesting_period_months INTEGER DEFAULT 48,
    total_options INTEGER NOT NULL,
    exercise_price REAL NOT NULL,
    vested_options INTEGER DEFAULT 0,
    exercised_options INTEGER DEFAULT 0,
    forfeited_options INTEGER DEFAULT 0,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

### 3.6 GST Domain

CREATE TABLE gst_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_type TEXT NOT NULL,
    filing_period TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filed_date TEXT,
    status TEXT DEFAULT 'pending',
    json_file_path TEXT,
    acknowledgement TEXT,
    tax_payable REAL DEFAULT 0,
    tax_paid REAL DEFAULT 0,
    late_fee REAL DEFAULT 0,
    interest REAL DEFAULT 0
);

CREATE TABLE itc_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    bill_id INTEGER,
    gstin_supplier TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    taxable_value REAL NOT NULL,
    igst REAL DEFAULT 0,
    cgst REAL DEFAULT 0,
    sgst REAL DEFAULT 0,
    total_tax REAL NOT NULL,
    eligible_itc INTEGER DEFAULT 1,
    claimed_in_return TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (bill_id) REFERENCES bills(id)
);

### 3.7 Tax Domain

CREATE TABLE tds_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_type TEXT NOT NULL,
    quarter TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filed_date TEXT,
    status TEXT DEFAULT 'pending',
    total_deducted REAL DEFAULT 0,
    total_deposited REAL DEFAULT 0,
    late_filing_fee REAL DEFAULT 0,
    json_file_path TEXT
);

CREATE TABLE tds_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tds_return_id INTEGER,
    deductee_name TEXT NOT NULL,
    deductee_pan TEXT,
    section TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    payment_amount REAL NOT NULL,
    tds_rate REAL NOT NULL,
    tds_amount REAL NOT NULL,
    surcharge REAL DEFAULT 0,
    cess REAL DEFAULT 0,
    total_tds REAL NOT NULL,
    deposit_date TEXT,
    challan_number TEXT,
    bsr_code TEXT,
    FOREIGN KEY (tds_return_id) REFERENCES tds_returns(id)
);

CREATE TABLE advance_tax (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fy TEXT NOT NULL,
    installment TEXT NOT NULL,
    due_date TEXT NOT NULL,
    paid_date TEXT,
    amount REAL NOT NULL,
    challan_number TEXT,
    bsr_code TEXT,
    status TEXT DEFAULT 'pending'
);

### 3.8 Ledger Domain

CREATE TABLE chart_of_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    sub_type TEXT,
    parent_id INTEGER,
    is_bank_account INTEGER DEFAULT 0,
    is_cash_account INTEGER DEFAULT 0,
    opening_balance REAL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES chart_of_accounts(id)
);

CREATE TABLE journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    reference TEXT,
    description TEXT NOT NULL,
    source TEXT,
    total_debit REAL NOT NULL,
    total_credit REAL NOT NULL,
    is_auto_generated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    description TEXT,
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
);

CREATE TABLE fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_name TEXT NOT NULL,
    asset_code TEXT UNIQUE,
    purchase_date TEXT NOT NULL,
    purchase_cost REAL NOT NULL,
    salvage_value REAL DEFAULT 0,
    useful_life_years INTEGER NOT NULL,
    depreciation_method TEXT DEFAULT 'wdv',
    accumulated_depreciation REAL DEFAULT 0,
    wdv REAL NOT NULL,
    disposal_date TEXT,
    disposal_amount REAL,
    status TEXT DEFAULT 'active'
);

### 3.9 Equity Domain

CREATE TABLE shareholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    pan TEXT,
    email TEXT,
    investment_date TEXT,
    investment_amount REAL,
    share_class TEXT,
    shares_held INTEGER,
    share_premium REAL DEFAULT 0,
    pre_money_valuation REAL,
    post_money_valuation REAL,
    anti_dilution TEXT,
    liquidation_preference REAL,
    board_seat INTEGER DEFAULT 0
);

CREATE TABLE safe_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investor_id INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    investment_amount REAL NOT NULL,
    valuation_cap REAL,
    discount_rate REAL,
    pro_rata_rights INTEGER DEFAULT 1,
    conversion_trigger TEXT,
    converted INTEGER DEFAULT 0,
    conversion_date TEXT,
    shares_issued INTEGER,
    FOREIGN KEY (investor_id) REFERENCES shareholders(id)
);

CREATE TABLE cap_table_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_diluted_shares INTEGER NOT NULL,
    esop_pool_shares INTEGER DEFAULT 0,
    esop_pool_pct REAL DEFAULT 0,
    snapshot_json TEXT NOT NULL
);

### 3.10 Forecast Domain

CREATE TABLE budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fy TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT,
    jan REAL DEFAULT 0,
    feb REAL DEFAULT 0,
    mar REAL DEFAULT 0,
    apr REAL DEFAULT 0,
    may REAL DEFAULT 0,
    jun REAL DEFAULT 0,
    jul REAL DEFAULT 0,
    aug REAL DEFAULT 0,
    sep REAL DEFAULT 0,
    oct REAL DEFAULT 0,
    nov REAL DEFAULT 0,
    dec REAL DEFAULT 0,
    annual_total REAL NOT NULL
);

CREATE TABLE forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_date TEXT NOT NULL,
    horizon_months INTEGER DEFAULT 12,
    scenario TEXT DEFAULT 'base',
    revenue_forecast REAL,
    burn_forecast REAL,
    headcount_forecast INTEGER,
    cash_forecast REAL,
    runway_forecast REAL,
    assumptions TEXT
);

### 3.11 Expense Domain

CREATE TABLE expense_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    claim_date TEXT NOT NULL,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    gst_amount REAL DEFAULT 0,
    vendor_name TEXT,
    description TEXT,
    receipt_document_id TEXT,
    status TEXT DEFAULT 'submitted',
    approved_by TEXT,
    approved_date TEXT,
    reimbursement_date TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (receipt_document_id) REFERENCES documents(id)
);

---

## 4. The Rust Sidecar — Expanded (v4.0)

The Rust sidecar grows from ~400 lines to ~1,200 lines, organized into modules. It remains a single 12 MB static binary.

### 4.1 Module Structure

src/
  main.rs              # HTTP server, routing, state
  lib.rs               # Public API
  intent/
    global.rs          # 8-dim global IntentVec
    payroll.rs         # 8-dim payroll sub-vector
    gst.rs             # 8-dim GST sub-vector
    tax.rs             # 8-dim tax sub-vector
    treasury.rs        # 8-dim treasury sub-vector
    revenue.rs         # 8-dim revenue sub-vector
    payables.rs        # 8-dim payables sub-vector
    equity.rs          # 8-dim equity sub-vector
    compliance.rs      # 8-dim compliance sub-vector
  fold/
    mod.rs             # Domain router, dispatch logic
    treasury.rs        # Treasury fold functions
    payroll.rs         # Payroll fold functions
    gst.rs             # GST fold functions
    tax.rs             # Tax fold functions
    revenue.rs         # Revenue fold functions
    payables.rs        # Payables fold functions
    equity.rs          # Equity fold functions
  validate/
    mod.rs             # Hierarchical validator
    rules.rs           # 18 CA-signed rules (YAML-loaded)
    domain/            # Per-domain validation logic
  unfold/
    mod.rs             # Response shape generator
    templates.rs       # Layout + flag logic
  critic/
    mod.rs             # Prior update logic
  tests/
    prop.rs            # Property-based tests
    integration.rs     # HTTP endpoint tests

### 4.2 The Domain Router

The Rust sidecar now routes by domain. Each domain has its own fold function that computes a specialized 8-dim sub-vector. The global 8-dim vector is always computed first, then domain-specific data is blended in.

Key design:
- Global fold runs on every request (cash, burn, runway, compliance posture)
- Domain fold runs only when domain data is provided (payroll health, GST status, etc.)
- Hierarchical validation checks global rules first, then domain rules
- Response shape includes both global and domain intent for rich rendering

### 4.3 Example: Payroll Domain Fold

The payroll sub-vector has 8 dimensions:
1. pf_compliance — ECR filed on time, wage ceiling respected
2. esi_compliance — ESI return filed, contribution correct
3. tds_accuracy — TDS computed matches deducted
4. pt_state — Professional tax filed for applicable states
5. lwf_state — Labour Welfare Fund contribution
6. gratuity_reserve — Adequacy of provision
7. bonus_reserve — Statutory bonus provision
8. leave_liability — Leave encashment provision

Each dimension is computed from payroll data and blended with the global intent (20% global influence, 80% domain-specific).

### 4.4 The 18 CA-Signed Rules (YAML)

Rules are loaded at startup from a YAML file. Each rule has:
- id — unique identifier (TREASURY-001, PAYROLL-001, etc.)
- domain — which module owns it
- description — human-readable
- statute — legal reference (CGST Act, Income Tax Act, etc.)
- section — specific section number
- condition — logic expression (evaluated against intent + snapshot)
- severity — info, warning, or block
- action — what to do when triggered

Example rules:
- TREASURY-001: Cash runway below 3 months + strong cash preservation intent = BLOCK
- PAYROLL-001: PF not deposited by 15th of following month = BLOCK
- GST-001: GSTR-3B filed after 20th = BLOCK (late fee: Rs.50/day)
- GST-002: ITC claimed > 105% of GSTR-2B = WARNING (Rule 36(4))
- TAX-001: Q1 advance tax < 15% of estimated = WARNING (234C interest)
- TAX-002: TDS not deposited by 7th = BLOCK (Rs.200/day penalty)
- PAYABLES-001: MSME vendor unpaid after 45 days = WARNING (MSMED Act)
- REVENUE-001: e-Invoice missing for turnover > Rs.5Cr = BLOCK
- EQUITY-001: ESOP pool > 10% without board approval = BLOCK
- COMPLIANCE-001: AOC-4 filed > 30 days after AGM = WARNING

---

## 5. The Python Layer — 12 Domain Services

The Python layer is organized into 12 domain services, each with:
- Data access layer (SQLAlchemy models)
- Business logic (service classes)
- API endpoints (FastAPI routers)
- Email templates (Jinja2)

A DomainRouter classifies incoming queries using keyword matching and routes to the appropriate service. Each service:
1. Fetches relevant domain data from SQLite
2. Calls the LLM (Maisha) to propose a narrative + action claim
3. Calls Mahsa (Rust) with domain context for fold/validate/unfold
4. Renders the response using the returned ResponseShape

---

## 6. The Email Channel — Expanded Templates

### 6.1 Daily 8pm CFO Brief (v4.0)

The daily brief now includes a Domain Health Dashboard — a scorecard showing the health of each domain module:

- Treasury: 92/100 (Healthy — 14.8 mo runway)
- GST: 78/100 (Warning — GSTR-3B for May not yet filed)
- Payroll: 95/100 (Healthy — June payroll processed)
- Tax: 64/100 (Alert — Q1 advance tax shortfall Rs.1.2L)
- Compliance: 88/100 (Healthy — 3 filings due, all on track)

Plus the usual sections: This Week, Needs Your Eyes, Approvals Pending, Strategic Prompt.

### 6.2 Compliance Alert Email

Domain-specific alert emails with:
- Due date and days remaining
- Required amount vs paid so far
- Shortfall calculation
- Interest/penalty risk
- Direct action button (Generate Challan, File Return, etc.)
- Rule citation (Rule ID, Statute, Section)

### 6.3 Payroll Approval Email

Detailed breakdown:
- Gross salary per employee
- PF, ESI, TDS, PT deductions
- Net payable
- Employer contributions
- Mahsa validation note (e.g., "Yellow — TDS variance of Rs.2,400 detected")
- Approve / Review buttons

### 6.4 Investor Update Email

Quarterly investor update generated automatically:
- KPI summary (ARR, burn, runway, headcount)
- Financial highlights (revenue, expenses, net burn)
- Operational updates (new hires, product launches)
- Forward-looking statements (next quarter goals)
- PDF attachment with full financials

---

## 7. The Web UI — FastAPI + HTMX

### 7.1 Dashboard Layout

+-------------------------------------------------------------+
|  Maisha-Mahsa v4.0                    [Ask Maisha] [Profile] |
+----------+--------------------------------------------------+
|          |  KPI STRIP                                         |
|  NAV     |  Cash: Rs.1.24Cr  Burn: Rs.8.4L/mo  Runway: 14.8mo   |
|          |  AR: Rs.45L  AP: Rs.12L  Payroll: Rs.4.3L  GST: Rs.2.1L  |
|  Dashboard|                                                   |
|  Treasury |  DOMAIN CARDS                                     |
|  Revenue  |  +--------+ +--------+ +--------+ +--------+   |
|  Payables |  |Treasury| | Payroll| |  GST   | |  Tax   |   |
|  Payroll  |  |  92/100| |  95/100| |  78/100| |  64/100|   |
|  GST      |  |   OK   | |   OK   | |   WARN | |   ALERT|   |
|  Tax      |  +--------+ +--------+ +--------+ +--------+   |
|  Equity   |                                                   |
|  Compliance|  CHARTS                                           |
|  Ledger   |  [Burn Trend] [Cash Flow] [Revenue]              |
|  Forecast |                                                   |
|  Expense  |  COMPLIANCE CALENDAR                              |
|  Vault    |  * 15 Jun: Advance Tax Q1 (DUE)                  |
|          |  * 18 Jun: GSTR-3B May (DUE in 3 days)            |
|          |  * 20 Jun: PF deposit Jun (DUE in 5 days)         |
|          |                                                   |
|          |  APPROVALS PENDING (4)                            |
|          |  OK Salary Jun 2026        Rs.4.32L  [Review]       |
|          |  WARN Vendor — AWS India   Rs.87K    [Review]       |
|          |  BLOCK CloudHost Pro       Rs.12K    [Blocked]      |
|          |  WARN TDS Q1 deposit       Rs.48K    [Review]       |
|          |                                                   |
|          |  STRATEGIC PROMPT                                 |
|          |  "Burn multiple improved to 1.4. Cleanest window   |
|          |   for investor conversations in 2 quarters."       |
|          |  [Draft Investor Update] [Skip]                   |
+----------+--------------------------------------------------+

### 7.2 Domain-Specific Pages

Each domain has a dedicated page with:
- KPI strip (domain-specific metrics)
- Action bar (create invoice, run payroll, file return, etc.)
- Data table (paginated, sortable, HTMX-powered)
- Charts (trend lines, donut charts via lightweight JS)
- Compliance status (next filing, health score)
- Quick actions ("Generate ECR", "File GSTR-3B", "Pay TDS")

### 7.3 The /cfo Strategy Panel (v4.0 enhanced)

- Scenario Engine: Base / +20% Revenue / -20% Revenue / Hire 2 more — see runway impact
- Bets Tracker: Budget vs spent vs ROI for each strategic initiative
- 90-Day Forward Calendar: All upcoming deadlines across all domains
- Investor Update Generator: One-click quarterly update with KPIs, financials, forward look
- Cap Table Snapshot: Founder / Investor / ESOP / Advisor breakdown + dilution modeling

---

## 8. The Complete Tech Stack (v4.0)

| Layer | Tool | License | Notes |
|---|---|---|---|
| Backend API | FastAPI | MIT | Async, Pydantic-native |
| Validation | Pydantic v2 | MIT | Zero runtime type errors |
| ORM | SQLAlchemy 2.0 async | MIT | Type-safe, 40+ tables |
| Migrations | Alembic | MIT | Versioned schema |
| Task queue | ARQ (Redis) | MIT | Async-native |
| Database | SQLite | Public domain | Single file, Git-friendly |
| Cache / sessions | Redis 7 | BSD | Local or cloud |
| PDF generation | WeasyPrint | BSD | Invoices, reports, challans |
| Excel/CSV | Polars + openpyxl | MIT/Apache | Fast export |
| HTTP client | httpx | BSD | Async |
| Email | aiosmtplib + Jinja2 | MIT | Self-hosted SMTP |
| Dev SMTP | MailHog | MIT | Local testing |
| LLM (Maisha) | Ollama + Qwen3-14B / Llama-3.3-8B | Apache 2.0 | Local = free + private |
| LLM fallback | Claude Opus 4.8 / Sonnet 4.6 (`claude-opus-4-8`, `claude-sonnet-4-6`) | — | Only if local disappoints |
| DIF sidecar (Mahsa) | Rust + axum + nalgebra | MIT/Apache | 12 MB static binary |
| OCR | Tesseract + invoice2data | Apache 2.0 | Invoice capture |
| Document vault | Local filesystem + SQLite index | — | 7-year retention |
| Backups | restic to Backblaze B2 | BSD | <10GB free tier |
| Hosting | Hetzner EUR 6/mo or laptop | — | EUR 6 = ~Rs.540 |
| UI | FastAPI + HTMX + vanilla CSS | MIT | No React, no build step |
| Charts | Chart.js (CDN) | MIT | Lightweight |

Total monthly cost: Rs.600-800.
- Hetzner VPS (2 vCPU, 4GB): EUR 6 ~ Rs.540
- Backblaze B2 backups: ~Rs.100 (for 10-20GB)
- Redis + SQLite + MailHog: Rs.0 (self-hosted)
- LLM: Rs.0 (local Ollama)

---

## 9. The 16-Week Build Plan (Solo)

### Phase 1: Foundation (Weeks 1-4)

Week 1 — Core Infrastructure
- Monorepo setup: api/ (Python/Poetry), dif/ (Rust/Cargo), infra/ (docker-compose)
- SQLite schema: all 40+ tables, Alembic migrations
- FastAPI skeleton, HTMX base template, auth (single password)
- Deploy to Hetzner VPS (or local)
- Deliverable: Hello-world dashboard live

Week 2 — Treasury + Banking
- Bank account model, CSV import (HDFC, ICICI, Axis formats)
- Transaction categorization engine
- Cash position, burn calculator, runway
- Bank reconciliation (auto-match algorithm)
- Deliverable: Upload bank CSV -> see cash, burn, runway

Week 3 — Revenue + Invoicing
- Customer master, invoice generation (GST-compliant)
- AR aging, dunning email engine
- Credit notes, revenue recognition
- Document vault (scan -> OCR -> store)
- Deliverable: Create invoice -> send to customer -> track AR

Week 4 — Payables + Vendor Management
- Vendor master, PO workflow, 3-way match
- Bill capture, AP aging
- TDS on payables (194C, 194J auto-calculation)
- MSME compliance flagging
- Deliverable: Full procure-to-pay workflow

### Phase 2: Compliance Engine (Weeks 5-8)

Week 5 — Payroll Engine
- Employee master, salary structure
- Monthly payroll computation (PF, ESI, PT, TDS)
- ECR generation, challan generation
- Payslip generation (PDF)
- Deliverable: Run June payroll -> generate ECR -> pay challan

Week 6 — GST Module
- GSTR-1 builder (B2B, B2C, HSN)
- GSTR-2B reconciliation, ITC register
- GSTR-3B computation + JSON generation
- e-Invoice readiness (IRN scaffold)
- Deliverable: File GSTR-3B for a test month

Week 7 — Income Tax + TDS
- TDS rate engine (all sections + thresholds)
- TDS return builder (24Q, 26Q)
- Advance tax calculator + challan
- Form 16 generation
- Deliverable: Generate Q1 TDS return + advance tax challan

Week 8 — Compliance Calendar + Rules Engine
- Compliance calendar (all domains, all forms)
- T-7, T-1, T-0 email alerts
- 18 CA-signed rules loaded into Rust validator
- CA walkthrough + sign-off
- Deliverable: All rules active, calendar alerting

### Phase 3: Intelligence Layer (Weeks 9-12)

Week 9 — Rust DIF Sidecar v4.0
- Port v3.0 sidecar to v4.0 (domain router + sub-vectors)
- 8 domain fold modules
- Hierarchical validator
- Property tests (proptest)
- Deliverable: cargo test passes, /fold endpoint live

Week 10 — Maisha (LLM) Integration
- Ollama setup, Qwen3-14B fine-tuning on Indian finance corpus
- Domain classifier, query router
- First end-to-end: "What is my GST liability?" -> Maisha -> Mahsa -> response
- Deliverable: Natural language queries working

Week 11 — Accounting + Ledger
- Chart of accounts (Indian GAAP)
- Journal entry engine (auto + manual)
- Trial balance, P&L, Balance sheet, Cash flow
- Fixed asset register + depreciation
- Deliverable: Monthly books close automatically

Week 12 — Forecasting + Budgeting
- Budget input UI, variance analysis
- Rolling 12-month forecast
- Scenario engine (base/optimistic/pessimistic)
- Burn multiple, unit economics
- Deliverable: CFO can model "hire 2 more" -> see runway impact

### Phase 4: Equity + Polish (Weeks 13-16)

Week 13 — Cap Table + Equity
- Shareholder register, ESOP tracking
- SAFE note modeling, conversion waterfall
- Investor reporting template
- Deliverable: Cap table accurate, SAFE terms modeled

Week 14 — Expense Management
- Expense claim workflow (photo -> OCR -> approval -> payment)
- Corporate card reconciliation
- Petty cash, reimbursement
- Deliverable: Employee submits expense -> you approve -> reimbursed

Week 15 — Audit + Document Vault
- 7-year retention policy, auto-archive
- Full-text search across documents
- Audit trail hash-chaining
- Statutory audit support package generation
- Deliverable: Auditor can download entire audit package in 1 click

Week 16 — Integration + v1.0
- End-to-end testing: 1 month parallel run
- Reconcile with existing process
- Fix the 10 things Maisha gets wrong
- Runbook, backup/restore tested
- Deliverable: v1.0 of your complete financial suite

Total: 16 weekends, ~240 hours. Solo. Rs.600-800/mo. You own the entire stack.

---

## 10. The Maisha-Mahsa Loop (v4.0)

+-------------------------------------------------------------+
|  USER QUERY (dashboard, email reply, or scheduled job)     |
+-----------------------------+-------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|  LAYER 0: Domain Router (Python)                            |
|  * Parse query -> classify domain (treasury, payroll, gst...) |
|  * Fetch domain data from SQLite                             |
|  * Latency target: <30ms                                    |
+-----------------------------+-------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|  LAYER 1: Maisha (Python, LLM)                              |
|  * Calls Ollama (Qwen3-14B) or Claude API                  |
|  * Tools: calculator, ledger_query, scenario_engine,          |
|           tax_calculator, gst_validator, payroll_engine     |
|  * Generates narrative + structured action_claim             |
|  * Latency target: <4s                                      |
+-----------------------------+-------------------------------+
                              | HTTP POST /fold
+-------------------------------------------------------------+
|  LAYER 2: Mahsa (Rust sidecar, 12 MB binary)                |
|  * Domain router -> dispatch to domain fold                 |
|  * Global 8-dim fold + domain sub-vector fold               |
|  * Hierarchical validation (18 rules)                      |
|  * Unfold to ResponseShape (layout, flags, banners)          |
|  * Latency: ~50-100 micros per call                         |
+-----------------------------+-------------------------------+
                              | JSON
                              v
+-------------------------------------------------------------+
|  LAYER 3: Renderer (Python, FastAPI)                        |
|  * Applies ResponseShape to dashboard / email              |
|  * Stores intent + validation in audit_log (hash-chained)  |
|  * Triggers approval emails for Yellow/Red                 |
|  * Updates compliance calendar on filings                   |
+-----------------------------+-------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|  LAYER 4: Email (aiosmtplib) + Document Vault (filesystem)   |
|  * Daily 8pm brief (domain health dashboard)               |
|  * Per-approval emails (domain-specific templates)           |
|  * Compliance alerts (T-7, T-1, T-0)                       |
|  * Exception reports (variance, threshold breach)          |
+-------------------------------------------------------------+

The Golden Rule (unchanged): Maisha never talks to the user directly. Mahsa is the gatekeeper. Every number Maisha generates is recomputed by Mahsa's deterministic engine. The hierarchical Intent IR makes every response explainable, every decision auditable, every rule enforcement provable.

---

## 11. Security & Audit Model

### 11.1 Data Security

| Layer | Measure |
|---|---|
| At rest | SQLite file on encrypted VPS disk (LUKS) |
| In transit | HTTPS via Caddy (auto TLS) |
| Backups | restic to Backblaze B2, encrypted client-side |
| Documents | SHA-256 per file, integrity check on access |
| Audit log | Append-only, hash-chained, tamper-evident |
| Auth | Single strong password + TOTP (optional) |
| Network | Tailscale for admin access, VPS firewall (ufw) |

### 11.2 Audit Trail

Every action generates an audit log entry with:
- Timestamp, action type, domain, user
- Global intent (8-dim JSON array)
- Domain intent (sub-vector JSON object)
- Validation status (green/yellow/red)
- Rules version
- Previous hash + this hash (SHA-256 chain)

The hash chain ensures that tampering with any historical record invalidates all subsequent hashes. An auditor can verify the entire chain in seconds.

---

## 12. Regulatory Compliance Matrix

| Regulation | Module | Key Requirements | Mahsa Rule |
|---|---|---|---|
| Companies Act 2013 | Compliance, Equity, Ledger | AOC-4, MGT-7, board minutes, audit | COMPLIANCE-001, COMPLIANCE-002, LEDGER-001 |
| Income Tax Act 1961 | Tax, Payroll | TDS deposit (7th), advance tax (Section 211), ITR | TAX-001, TAX-002, PAYROLL-002 |
| CGST Act 2017 | GST | GSTR-3B (20th), GSTR-1, ITC rules, e-invoice | GST-001, GST-002, REVENUE-001 |
| EPF Act 1952 | Payroll | ECR by 15th, 12% contribution, UAN | PAYROLL-001 |
| ESI Act 1948 | Payroll | Monthly return, 3.25%/0.75% contribution | PAYROLL-002 |
| PT Act (state-wise) | Payroll | Monthly deposit, state slabs | payroll.pt_state |
| MSMED Act 2006 | Payables | Payment within 45 days to MSME | PAYABLES-001 |
| FEMA 1999 | Revenue | Export invoicing, LUT, realization | revenue.fx_compliance |
| Payment of Bonus Act | Payroll | 8.33% minimum, Rs.21K wage ceiling | payroll.bonus_reserve |
| Payment of Gratuity Act | Payroll | 5-year eligibility, 15 days/year | payroll.gratuity_reserve |
| SEBI (SBEB) Regulations | Equity | ESOP disclosures, vesting rules | EQUITY-001 |
| DPIIT Startup India | Compliance | Periodic reporting, tax holiday | compliance.dpiit_tracking |

---

## 13. What Survives from v3.0

1. Rust DIF sidecar — expanded but core pattern unchanged
2. 8-dim global Intent IR — still governs overall approval mode
3. Email channel — expanded templates, same transport
4. Single-user architecture — SQLite, one password, solo buildable
5. English-only lock — no Indic work
6. 7-year audit log — hash-chained, append-only
7. Maisha-Mahsa validation pattern — every LLM output folded, validated, unfolded
8. Open-source, no paid APIs — Ollama, self-hosted SMTP, free tiers

---

## 14. What is New in v4.0

1. 12 domain modules — complete startup finance coverage
2. Hierarchical Intent IR — global 8-dim + 8 domain sub-vectors
3. 40+ table SQLite schema — full relational model
4. 18 CA-signed rules — covering all major Indian regulations
5. Compliance calendar — T-7, T-1, T-0 alerts across all domains
6. Document vault — OCR, full-text search, 7-year retention
7. Cap table + ESOP — SAFE modeling, conversion waterfall
8. Forecasting + budgeting — scenario engine, burn multiple
9. Expense management — photo -> OCR -> approval -> reimbursement
10. Investor reporting — quarterly update generator, KPI dashboard
11. 16-week build plan — still solo, still buildable
12. Domain health dashboard — scorecard in daily email + web UI

---

## 15. Next Steps

This PRD is build-ready. The recommended starting order:

1. This weekend: Set up monorepo, SQLite schema, FastAPI skeleton, deploy to Hetzner
2. Week 2: Treasury module (bank CSV import -> cash/burn/runway)
3. Week 5: Payroll module (the most complex domain — get it right early)
4. Week 9: Rust sidecar v4.0 (domain router + sub-vectors)
5. Week 16: v1.0 ship

If you want me to build any specific piece now:
- Complete schema.sql with all 40+ tables, indexes, and constraints
- Full Rust sidecar v4.0 source code (all 8 domain fold modules)
- Docker Compose for full stack (Python API + Rust DIF + Redis + MailHog + Ollama)
- Complete Jinja2 email template set (daily brief, compliance alerts, payroll approvals, etc.)
- HTMX dashboard templates (domain cards, data tables, forms)
- Indian GAAP chart of accounts (SQL insert statements)
- TDS rate engine YAML (all sections, thresholds, surcharge, cess)

Tell me which asset to generate first.
