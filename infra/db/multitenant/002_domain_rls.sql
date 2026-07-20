-- MMX-1.0 §WS4.1 — domain tables, tenant-scoped. This file demonstrates the RLS pattern EVERY
-- domain table follows; the full 36-table replay from SQLite is WS4.2 migration engineering, and
-- each migrated table ships its org_id + RLS in the same migration or CI fails (§0.8,
-- scripts/check_rls_coverage.sh). Money is BIGINT paise. Reg-scoped tables (GST) also carry
-- gstin_registration_id (G6). Included here: bills, invoices, journal_entries, gst_returns.

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

GRANT SELECT, INSERT, UPDATE, DELETE ON bills, invoices, journal_entries, gst_returns TO maisha_app;
