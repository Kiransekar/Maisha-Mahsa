-- MMX-1.0 §WS4.1 — domain tables, tenant-scoped. This file demonstrates the RLS pattern EVERY
-- domain table follows; the full 36-table replay from SQLite is WS4.2 migration engineering, and
-- each migrated table ships its org_id + RLS in the same migration or CI fails (§0.8,
-- scripts/check_rls_coverage.sh). Money is BIGINT paise. Reg-scoped tables (GST) also carry
-- gstin_registration_id (G6). Included here (WS4.7 widened the sample to the money/PII-bearing
-- tables the red-team targets): bills, invoices, journal_entries, gst_returns, vendors, customers,
-- bank_accounts, employees, tds_returns, documents.

CREATE TABLE bills (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  vendor_id   uuid,
  bill_number text NOT NULL,
  bill_date   date NOT NULL,
  subtotal    bigint NOT NULL,        -- paise (taxable value)
  tds_amount  bigint NOT NULL DEFAULT 0,
  total_amount bigint NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bills_org ON bills(org_id);

CREATE TABLE invoices (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  gstin_registration_id uuid REFERENCES gstin_registrations(id) ON DELETE SET NULL,
  invoice_number text NOT NULL,
  invoice_date date NOT NULL,
  taxable_value bigint NOT NULL,      -- paise
  total_tax   bigint NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invoices_org ON invoices(org_id);

CREATE TABLE journal_entries (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  entry_date  date NOT NULL,
  narration   text,
  amount      bigint NOT NULL,        -- paise
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX journal_entries_org ON journal_entries(org_id);

CREATE TABLE gst_returns (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  gstin_registration_id uuid NOT NULL REFERENCES gstin_registrations(id) ON DELETE CASCADE,
  return_type text NOT NULL,
  filing_period text NOT NULL,
  tax_payable bigint NOT NULL DEFAULT 0,  -- paise (cash)
  late_fee    bigint NOT NULL DEFAULT 0,
  interest    bigint NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX gst_returns_org ON gst_returns(org_id);

-- ---- money/PII-bearing domain tables (WS4.7 red-team targets) --------------------------
-- vendors / customers carry PAN + GSTIN (PII); same tenant-scoped pattern.
CREATE TABLE vendors (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name        text NOT NULL,
  pan         text,                    -- PII
  gstin       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vendors_org ON vendors(org_id);

CREATE TABLE customers (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name        text NOT NULL,
  pan         text,                    -- PII
  gstin       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX customers_org ON customers(org_id);

-- bank_accounts: account number + IFSC are PII; balance is money (paise).
CREATE TABLE bank_accounts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id      uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  account_number text NOT NULL,        -- PII
  ifsc           text NOT NULL,
  balance        bigint NOT NULL DEFAULT 0,   -- paise
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bank_accounts_org ON bank_accounts(org_id);

-- employees: PAN/UAN + salary are PII/money.
CREATE TABLE employees (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  name         text NOT NULL,          -- PII
  pan          text,                   -- PII
  uan          text,                   -- PII
  gross_salary bigint NOT NULL DEFAULT 0,   -- paise
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX employees_org ON employees(org_id);

-- tds_returns: reg-scoped statutory return (deductor-side).
CREATE TABLE tds_returns (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id   uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  form_type   text NOT NULL,           -- 24Q/26Q/27Q (regime-aware, WS1.A)
  quarter     text NOT NULL,           -- e.g. 2026-Q1
  total_tds   bigint NOT NULL DEFAULT 0,   -- paise
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tds_returns_org ON tds_returns(org_id);

-- documents: the DB-side of object-storage tenancy. storage_prefix is the tenant-scoped path
-- (e.g. 'org/<org_id>/...') that WS4.1 isolates in the bucket; RLS here proves org A can never
-- reach a row — hence a storage_prefix — that belongs to org B (real bucket ACL red-teaming is
-- WS4.2/WS4.3, see rls_redteam.sql header).
CREATE TABLE documents (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  entity_id      uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  doc_type       text NOT NULL,
  storage_prefix text NOT NULL,        -- tenant-scoped object-storage path
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_org ON documents(org_id);

-- ---- RLS: org_id = the session org, on every table (§0.8) -----------------------------
ALTER TABLE bills            ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills            FORCE  ROW LEVEL SECURITY;
CREATE POLICY bills_tenant ON bills
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE invoices         ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices         FORCE  ROW LEVEL SECURITY;
CREATE POLICY invoices_tenant ON invoices
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE journal_entries  ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entries  FORCE  ROW LEVEL SECURITY;
CREATE POLICY journal_entries_tenant ON journal_entries
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE gst_returns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gst_returns      FORCE  ROW LEVEL SECURITY;
CREATE POLICY gst_returns_tenant ON gst_returns
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE vendors          ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendors          FORCE  ROW LEVEL SECURITY;
CREATE POLICY vendors_tenant ON vendors
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE customers        ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers        FORCE  ROW LEVEL SECURITY;
CREATE POLICY customers_tenant ON customers
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE bank_accounts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts    FORCE  ROW LEVEL SECURITY;
CREATE POLICY bank_accounts_tenant ON bank_accounts
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE employees        ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees        FORCE  ROW LEVEL SECURITY;
CREATE POLICY employees_tenant ON employees
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE tds_returns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tds_returns      FORCE  ROW LEVEL SECURITY;
CREATE POLICY tds_returns_tenant ON tds_returns
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

ALTER TABLE documents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents        FORCE  ROW LEVEL SECURITY;
CREATE POLICY documents_tenant ON documents
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT, UPDATE, DELETE ON
  bills, invoices, journal_entries, gst_returns,
  vendors, customers, bank_accounts, employees, tds_returns, documents
  TO maisha_app;
