-- Maisha-Mahsa schema (PRD §3). Authoritative builder is SQLAlchemy
-- (`Base.metadata.create_all`); this file mirrors it for review/audit and bootstrap.
--
-- DEVIATION FROM PRD: money columns are INTEGER **paise**, not REAL, for exactness
-- (CLAUDE.md §2). Tables for not-yet-built domains are added as their modules land
-- (see BUILD_PROGRESS.md). Currently: shared + treasury.

PRAGMA foreign_keys = ON;

-- ---------- Shared (PRD §3.1) ----------
CREATE TABLE IF NOT EXISTS company (
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

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'founder',
    expertise TEXT DEFAULT 'founder',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    domain TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT,
    intent_global TEXT,        -- JSON array
    intent_domain TEXT,        -- JSON array
    validation_status TEXT,
    rules_version TEXT NOT NULL,
    prev_hash TEXT,
    this_hash TEXT
);

CREATE TABLE IF NOT EXISTS compliance_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    form_name TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filing_period TEXT,
    status TEXT DEFAULT 'pending',
    filed_date TEXT,
    acknowledgement TEXT,
    penalty_amount INTEGER DEFAULT 0,    -- paise
    reminder_sent INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rules_registry (
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,                  -- SHA-256 of content
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    domain TEXT,
    entity_id TEXT,
    ocr_text TEXT,
    upload_date TEXT NOT NULL,
    retention_until TEXT,                 -- NULL = permanent
    sha256 TEXT NOT NULL,
    tags TEXT,
    uploaded_by TEXT,
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_this_hash ON audit_log(this_hash);
CREATE INDEX IF NOT EXISTS idx_compliance_due ON compliance_calendar(due_date, status);
CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain, doc_type);

-- ---------- Treasury (PRD §3.2) ----------
CREATE TABLE IF NOT EXISTS bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc TEXT NOT NULL,
    account_type TEXT,
    opening_balance INTEGER DEFAULT 0,   -- paise
    current_balance INTEGER DEFAULT 0,   -- paise
    currency TEXT DEFAULT 'INR',
    is_primary INTEGER DEFAULT 0,
    last_sync TEXT
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    txn_date TEXT NOT NULL,
    description TEXT,
    reference TEXT,
    debit INTEGER DEFAULT 0,             -- paise
    credit INTEGER DEFAULT 0,            -- paise
    balance INTEGER,                     -- paise
    category TEXT,
    matched_invoice_id INTEGER,
    matched_vendor_id INTEGER,
    is_reconciled INTEGER DEFAULT 0,
    FOREIGN KEY (account_id) REFERENCES bank_accounts(id)
);

CREATE TABLE IF NOT EXISTS fixed_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER,
    fd_number TEXT NOT NULL,
    principal INTEGER NOT NULL,          -- paise
    interest_rate REAL NOT NULL,
    start_date TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    maturity_amount INTEGER,             -- paise
    tds_deducted INTEGER DEFAULT 0,      -- paise
    status TEXT DEFAULT 'active',
    FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_txn_account_date ON bank_transactions(account_id, txn_date);

-- ---------- Payroll (PRD §3.5) ----------
CREATE TABLE IF NOT EXISTS employees (
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
    state TEXT,
    bank_account TEXT,
    ifsc TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS salary_structures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    basic INTEGER NOT NULL,              -- paise
    hra INTEGER NOT NULL,
    lta INTEGER DEFAULT 0,
    special_allowance INTEGER DEFAULT 0,
    employer_pf INTEGER NOT NULL,
    employer_esi INTEGER DEFAULT 0,
    employee_pf INTEGER NOT NULL,
    employee_esi INTEGER DEFAULT 0,
    professional_tax INTEGER DEFAULT 0,
    tds_monthly INTEGER DEFAULT 0,
    gross_salary INTEGER NOT NULL,
    net_salary INTEGER NOT NULL,
    ctc INTEGER NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_year TEXT NOT NULL,
    run_date TEXT NOT NULL,
    total_gross INTEGER DEFAULT 0,
    total_deductions INTEGER DEFAULT 0,
    total_net INTEGER DEFAULT 0,
    total_pf_employer INTEGER DEFAULT 0,
    total_esi_employer INTEGER DEFAULT 0,
    status TEXT DEFAULT 'draft',
    ecr_generated INTEGER DEFAULT 0,
    ecr_file_path TEXT
);

CREATE TABLE IF NOT EXISTS payroll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payroll_run_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    gross INTEGER NOT NULL,
    basic INTEGER NOT NULL,
    hra INTEGER NOT NULL,
    lta INTEGER DEFAULT 0,
    special_allowance INTEGER DEFAULT 0,
    employee_pf INTEGER NOT NULL,
    employee_esi INTEGER DEFAULT 0,
    professional_tax INTEGER DEFAULT 0,
    tds INTEGER DEFAULT 0,
    other_deductions INTEGER DEFAULT 0,
    employer_pf INTEGER DEFAULT 0,
    employer_esi INTEGER DEFAULT 0,
    net_pay INTEGER NOT NULL,
    FOREIGN KEY (payroll_run_id) REFERENCES payroll_runs(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS esop_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    grant_date TEXT NOT NULL,
    vesting_start_date TEXT NOT NULL,
    cliff_months INTEGER DEFAULT 12,
    vesting_period_months INTEGER DEFAULT 48,
    total_options INTEGER NOT NULL,
    exercise_price INTEGER NOT NULL,     -- paise
    vested_options INTEGER DEFAULT 0,
    exercised_options INTEGER DEFAULT 0,
    forfeited_options INTEGER DEFAULT 0,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE INDEX IF NOT EXISTS idx_salary_emp ON salary_structures(employee_id, effective_from);
CREATE INDEX IF NOT EXISTS idx_payroll_entry_run ON payroll_entries(payroll_run_id);

-- ---------- GST (PRD §3.6) ----------
CREATE TABLE IF NOT EXISTS gst_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_type TEXT NOT NULL,
    filing_period TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filed_date TEXT,
    status TEXT DEFAULT 'pending',
    json_file_path TEXT,
    acknowledgement TEXT,
    tax_payable INTEGER DEFAULT 0,        -- paise (cash)
    tax_paid INTEGER DEFAULT 0,
    late_fee INTEGER DEFAULT 0,
    interest INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS itc_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    bill_id INTEGER,
    gstin_supplier TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    taxable_value INTEGER NOT NULL,       -- paise
    igst INTEGER DEFAULT 0,
    cgst INTEGER DEFAULT 0,
    sgst INTEGER DEFAULT 0,
    total_tax INTEGER NOT NULL,
    eligible_itc INTEGER DEFAULT 1,
    in_2b INTEGER DEFAULT 0,
    claimed_in_return TEXT
);

CREATE INDEX IF NOT EXISTS idx_gst_return_period ON gst_returns(return_type, filing_period);

-- ---------- Revenue (PRD §3.3) ----------
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pan TEXT,
    gstin TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    state TEXT,
    payment_terms INTEGER DEFAULT 30,
    tds_applicable INTEGER DEFAULT 0,
    tds_section TEXT,
    tds_rate REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    invoice_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    subtotal INTEGER NOT NULL,            -- paise (taxable)
    gst_rate REAL DEFAULT 0,
    igst_amount INTEGER DEFAULT 0,
    cgst_amount INTEGER DEFAULT 0,
    sgst_amount INTEGER DEFAULT 0,
    total_amount INTEGER NOT NULL,
    tds_amount INTEGER DEFAULT 0,
    net_receivable INTEGER NOT NULL,
    irn TEXT,
    qr_code_path TEXT,
    status TEXT DEFAULT 'draft',
    paid_date TEXT,
    paid_amount INTEGER DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    hsn_code TEXT,
    quantity INTEGER DEFAULT 1,
    rate INTEGER NOT NULL,                -- paise per unit
    amount INTEGER NOT NULL,              -- paise
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_note_number TEXT UNIQUE NOT NULL,
    invoice_id INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    reason TEXT,
    amount INTEGER NOT NULL,              -- paise
    gst_adjustment INTEGER DEFAULT 0,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE INDEX IF NOT EXISTS idx_invoice_customer ON invoices(customer_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoice_item_inv ON invoice_items(invoice_id);

-- ---------- Payables (PRD §3.4) ----------
CREATE TABLE IF NOT EXISTS vendors (
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
    payee_type TEXT DEFAULT 'company',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT UNIQUE NOT NULL,
    vendor_id INTEGER NOT NULL,
    po_date TEXT NOT NULL,
    delivery_date TEXT,
    total_amount INTEGER NOT NULL,        -- paise
    received_amount INTEGER DEFAULT 0,    -- GRN value, paise
    status TEXT DEFAULT 'open',
    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL,
    vendor_id INTEGER NOT NULL,
    po_id INTEGER,
    bill_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    subtotal INTEGER NOT NULL,            -- paise (taxable)
    gst_amount INTEGER DEFAULT 0,
    igst_amount INTEGER DEFAULT 0,
    cgst_amount INTEGER DEFAULT 0,
    sgst_amount INTEGER DEFAULT 0,
    tds_amount INTEGER DEFAULT 0,
    total_amount INTEGER NOT NULL,        -- payable = subtotal + gst - tds
    itc_eligible INTEGER DEFAULT 1,
    status TEXT DEFAULT 'open',
    paid_date TEXT,
    paid_amount INTEGER DEFAULT 0,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
);

CREATE INDEX IF NOT EXISTS idx_bill_vendor ON bills(vendor_id, bill_date);

-- ---------- Tax (PRD §3.7) ----------
CREATE TABLE IF NOT EXISTS tds_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_type TEXT NOT NULL,            -- 24Q / 26Q / 27Q
    quarter TEXT NOT NULL,
    due_date TEXT NOT NULL,
    filed_date TEXT,
    status TEXT DEFAULT 'pending',
    total_deducted INTEGER DEFAULT 0,     -- paise
    total_deposited INTEGER DEFAULT 0,
    late_filing_fee INTEGER DEFAULT 0,
    json_file_path TEXT
);

CREATE TABLE IF NOT EXISTS tds_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tds_return_id INTEGER,
    deductee_name TEXT NOT NULL,
    deductee_pan TEXT,
    section TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    payment_amount INTEGER NOT NULL,      -- paise
    tds_rate REAL DEFAULT 0,
    tds_amount INTEGER NOT NULL,          -- paise
    surcharge INTEGER DEFAULT 0,
    cess INTEGER DEFAULT 0,
    total_tds INTEGER NOT NULL,
    deposit_date TEXT,
    challan_number TEXT,
    bsr_code TEXT,
    FOREIGN KEY (tds_return_id) REFERENCES tds_returns(id)
);

CREATE TABLE IF NOT EXISTS advance_tax (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fy TEXT NOT NULL,
    installment TEXT NOT NULL,
    due_date TEXT NOT NULL,
    paid_date TEXT,
    amount INTEGER NOT NULL,              -- paise
    challan_number TEXT,
    bsr_code TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_tds_entry_return ON tds_entries(tds_return_id);
CREATE INDEX IF NOT EXISTS idx_advance_tax_fy ON advance_tax(fy, installment);

-- ---------- Ledger / Accounting (PRD §3.8) ----------
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,           -- asset/liability/equity/income/expense
    sub_type TEXT,
    parent_id INTEGER,
    is_bank_account INTEGER DEFAULT 0,
    is_cash_account INTEGER DEFAULT 0,
    opening_balance INTEGER DEFAULT 0,    -- paise
    FOREIGN KEY (parent_id) REFERENCES chart_of_accounts(id)
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    reference TEXT,
    description TEXT NOT NULL,
    source TEXT,
    total_debit INTEGER NOT NULL,         -- paise
    total_credit INTEGER NOT NULL,
    is_auto_generated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit INTEGER DEFAULT 0,              -- paise
    credit INTEGER DEFAULT 0,            -- paise
    description TEXT,
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_name TEXT NOT NULL,
    asset_code TEXT UNIQUE,
    purchase_date TEXT NOT NULL,
    purchase_cost INTEGER NOT NULL,       -- paise
    salvage_value INTEGER DEFAULT 0,
    useful_life_years INTEGER NOT NULL,
    depreciation_method TEXT DEFAULT 'wdv',
    depreciation_rate REAL DEFAULT 0,
    accumulated_depreciation INTEGER DEFAULT 0,
    wdv INTEGER NOT NULL,                 -- paise
    disposal_date TEXT,
    disposal_amount INTEGER,
    status TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_journal_line_entry ON journal_lines(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_journal_line_account ON journal_lines(account_id);

-- ---------- Equity (PRD §3.9) ----------
CREATE TABLE IF NOT EXISTS shareholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,               -- founder/investor/esop/advisor
    pan TEXT,
    email TEXT,
    investment_date TEXT,
    investment_amount INTEGER DEFAULT 0,  -- paise
    share_class TEXT,
    shares_held INTEGER DEFAULT 0,
    share_premium INTEGER DEFAULT 0,      -- paise
    pre_money_valuation INTEGER,
    post_money_valuation INTEGER,
    anti_dilution TEXT,
    liquidation_preference REAL,
    board_seat INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS safe_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investor_id INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    investment_amount INTEGER NOT NULL,   -- paise
    valuation_cap INTEGER,                -- paise
    discount_rate REAL DEFAULT 0,
    pro_rata_rights INTEGER DEFAULT 1,
    conversion_trigger TEXT,
    converted INTEGER DEFAULT 0,
    conversion_date TEXT,
    shares_issued INTEGER,
    FOREIGN KEY (investor_id) REFERENCES shareholders(id)
);

CREATE TABLE IF NOT EXISTS cap_table_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_diluted_shares INTEGER NOT NULL,
    esop_pool_shares INTEGER DEFAULT 0,
    esop_pool_pct REAL DEFAULT 0,
    esop_board_approved INTEGER DEFAULT 1,
    snapshot_json TEXT NOT NULL
);

-- ---------- Forecast / Budgeting (PRD §3.10) ----------
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fy TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT,
    jan INTEGER DEFAULT 0, feb INTEGER DEFAULT 0, mar INTEGER DEFAULT 0,
    apr INTEGER DEFAULT 0, may INTEGER DEFAULT 0, jun INTEGER DEFAULT 0,
    jul INTEGER DEFAULT 0, aug INTEGER DEFAULT 0, sep INTEGER DEFAULT 0,
    oct INTEGER DEFAULT 0, nov INTEGER DEFAULT 0, dec INTEGER DEFAULT 0,
    annual_total INTEGER NOT NULL                 -- paise
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_date TEXT NOT NULL,
    horizon_months INTEGER DEFAULT 12,
    scenario TEXT DEFAULT 'base',
    revenue_forecast INTEGER,                     -- paise
    burn_forecast INTEGER,                        -- paise/month
    headcount_forecast INTEGER,
    cash_forecast INTEGER,                        -- projected min cash, paise
    runway_forecast REAL,                         -- months
    assumptions TEXT
);

-- ---------- Expense (PRD §3.11) ----------
CREATE TABLE IF NOT EXISTS expense_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    claim_date TEXT NOT NULL,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL,              -- paise
    gst_amount INTEGER DEFAULT 0,
    vendor_name TEXT,
    description TEXT,
    receipt_document_id TEXT,
    over_policy INTEGER DEFAULT 0,
    status TEXT DEFAULT 'submitted',
    approved_by TEXT,
    approved_date TEXT,
    reimbursement_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (receipt_document_id) REFERENCES documents(id)
);
