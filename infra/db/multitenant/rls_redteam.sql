-- MMX-1.0 §WS4.7 — tenancy red-team suite (DB / RLS layer).
--
-- SCOPE HONESTY: this proves the *database* half of tenant isolation — that Postgres RLS keeps
-- one org's session from reading, writing, updating, deleting, or otherwise reaching another
-- org's rows (the DB analogue of a cross-tenant object-storage path, via documents.storage_prefix).
-- ROUTE-level red-teaming (a forged org_id in a request body, a mis-scoped handler, an IDOR on a
-- REST path) and REAL object-storage red-teaming (bucket ACLs / signed-URL scoping) need the app
-- tenancy + auth layers that land in WS4.2 (app scoping) and WS4.3 (session/JWT → app.current_org).
-- Until those exist there is no live session context to attack; this file is the RLS foundation
-- they build on, not the whole of WS4.7.
--
-- Method: provision two orgs and one row per protected table as the privileged owner (owner
-- bypasses RLS — the only place rows cross org lines), then drop to the non-superuser app role
-- and run a NEGATIVE matrix: for every protected table, org A's session must
--   (SELECT)  see 0 of org B's rows          — and exactly its own 1 row (positive control);
--   (INSERT)  be rejected when tagging org B  — WITH CHECK blocks the cross-org write;
--   (UPDATE)  touch 0 of org B's rows         — USING hides them;
--   (DELETE)  touch 0 of org B's rows;
--   (UNBOUND) see 0 rows with no org set      — fail-closed.
-- Any ASSERT/RAISE failure aborts psql non-zero, so a single leak fails the gate.
\set ON_ERROR_STOP on

-- ---- provisioning (privileged; owner bypasses RLS) ------------------------------------
INSERT INTO orgs (id, name) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Org A'),
  ('22222222-2222-2222-2222-222222222222', 'Org B');
INSERT INTO entities (id, org_id, legal_name) VALUES
  ('a1111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'A Ltd'),
  ('b2222222-2222-2222-2222-222222222222', '22222222-2222-2222-2222-222222222222', 'B Ltd');
INSERT INTO gstin_registrations (id, org_id, entity_id, gstin, state_code) VALUES
  ('ca111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', '27AAAAA0000A1Z5', '27'),
  ('cb222222-2222-2222-2222-222222222222', '22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', '29BBBBB0000B1Z5', '29');

INSERT INTO bills (org_id, entity_id, bill_number, bill_date, subtotal, total_amount) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'A-1', '2026-04-01', 100000, 100000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'B-1', '2026-04-01', 200000, 200000);
INSERT INTO invoices (org_id, entity_id, gstin_registration_id, invoice_number, invoice_date, taxable_value) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'ca111111-1111-1111-1111-111111111111', 'INV-A', '2026-04-01', 100000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'cb222222-2222-2222-2222-222222222222', 'INV-B', '2026-04-01', 200000);
INSERT INTO journal_entries (org_id, entity_id, entry_date, amount) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', '2026-04-01', 100000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', '2026-04-01', 200000);
INSERT INTO gst_returns (org_id, gstin_registration_id, return_type, filing_period) VALUES
  ('11111111-1111-1111-1111-111111111111', 'ca111111-1111-1111-1111-111111111111', 'GSTR-3B', '2026-04'),
  ('22222222-2222-2222-2222-222222222222', 'cb222222-2222-2222-2222-222222222222', 'GSTR-3B', '2026-04');
INSERT INTO vendors (org_id, entity_id, name, pan) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'Vendor A', 'AAAPA0000A'),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'Vendor B', 'BBBPB0000B');
INSERT INTO customers (org_id, entity_id, name, pan) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'Customer A', 'AAAPC0000A'),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'Customer B', 'BBBPC0000B');
INSERT INTO bank_accounts (org_id, entity_id, account_number, ifsc, balance) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', '000111000111', 'HDFC0000001', 5000000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', '000222000222', 'ICIC0000002', 7000000);
INSERT INTO employees (org_id, entity_id, name, pan, gross_salary) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'Emp A', 'AAAPE0000A', 5000000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'Emp B', 'BBBPE0000B', 6000000);
INSERT INTO tds_returns (org_id, entity_id, form_type, quarter, total_tds) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', '26Q', '2026-Q1', 100000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', '26Q', '2026-Q1', 200000);
INSERT INTO documents (org_id, entity_id, doc_type, storage_prefix) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'invoice_pdf', 'org/11111111-1111-1111-1111-111111111111/invoices/A-1.pdf'),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'invoice_pdf', 'org/22222222-2222-2222-2222-222222222222/invoices/B-1.pdf');

-- everything below runs as the application role, subject to RLS.
SET ROLE maisha_app;

-- ---- the negative matrix: every op × every protected table ----------------------------
DO $$
DECLARE
  orgA constant uuid := '11111111-1111-1111-1111-111111111111';
  orgB constant uuid := '22222222-2222-2222-2222-222222222222';
  t    text;
  cols text;
  n    integer;
  blocked boolean;
  -- every tenant-scoped table carrying org_id (id has a default; clone-insert relies on both).
  tables text[] := ARRAY[
    'entities','gstin_registrations',
    'bills','invoices','journal_entries','gst_returns',
    'vendors','customers','bank_accounts','employees','tds_returns','documents'
  ];
BEGIN
  PERFORM set_config('app.current_org', orgA::text, false);  -- authenticated as org A

  FOREACH t IN ARRAY tables LOOP
    -- (SELECT) org A must not see any org-B row...
    EXECUTE format('SELECT count(*) FROM %I WHERE org_id = $1', t) INTO n USING orgB;
    ASSERT n = 0, format('LEAK: org A read %s of org B''s rows on table %s', n, t);
    -- ...and must see exactly its own seeded row (positive control — visibility isn't broken).
    EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
    ASSERT n = 1, format('org A should see exactly 1 own row on %s, saw %s', t, n);

    -- (INSERT) clone A's own (fully valid) row but tag it org B → WITH CHECK must reject it.
    -- Cloning every column except id/org_id keeps all NOT NULLs satisfied, so the ONLY reason
    -- the insert can fail is the RLS WITH CHECK — not an incidental constraint.
    EXECUTE format(
      'SELECT string_agg(quote_ident(column_name), '','') FROM information_schema.columns '
      'WHERE table_name = %L AND column_name NOT IN (''id'',''org_id'')', t) INTO cols;
    BEGIN
      EXECUTE format('INSERT INTO %I (org_id, %s) SELECT $1, %s FROM %I WHERE org_id = $2 LIMIT 1',
                     t, cols, cols, t) USING orgB, orgA;
      blocked := false;
    EXCEPTION WHEN others THEN
      blocked := true;
    END;
    ASSERT blocked, format('LEAK: cross-org INSERT was NOT blocked on table %s', t);

    -- (UPDATE) org B's rows are invisible → 0 rows affected.
    EXECUTE format('UPDATE %I SET org_id = org_id WHERE org_id = $1', t) USING orgB;
    GET DIAGNOSTICS n = ROW_COUNT;
    ASSERT n = 0, format('LEAK: cross-org UPDATE touched %s rows on table %s', n, t);

    -- (DELETE) likewise → 0 rows affected.
    EXECUTE format('DELETE FROM %I WHERE org_id = $1', t) USING orgB;
    GET DIAGNOSTICS n = ROW_COUNT;
    ASSERT n = 0, format('LEAK: cross-org DELETE touched %s rows on table %s', n, t);
  END LOOP;

  -- (UNBOUND) fail-closed: with no org bound, RLS matches nothing on every table.
  PERFORM set_config('app.current_org', '', false);
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
    ASSERT n = 0, format('LEAK: unbound session saw %s rows on table %s (not fail-closed)', n, t);
  END LOOP;
END $$;

-- ---- storage-prefix isolation (the DB analogue of a cross-tenant object-storage path) --
-- Org A must never reach a documents row — and therefore never learn the storage_prefix — that
-- belongs to org B, even when it knows/guesses B's org_id or path. This is the row-level guard
-- that a compromised or buggy app path would otherwise bypass; the bucket-ACL equivalent is
-- WS4.2/WS4.3 (see header).
SET app.current_org = '11111111-1111-1111-1111-111111111111';
DO $$
DECLARE n integer;
BEGIN
  -- by B's org_id
  SELECT count(*) INTO n FROM documents WHERE org_id = '22222222-2222-2222-2222-222222222222';
  ASSERT n = 0, 'LEAK: org A reached a documents row belonging to org B';
  -- by B's storage path prefix
  SELECT count(*) INTO n FROM documents WHERE storage_prefix LIKE 'org/22222222-%';
  ASSERT n = 0, 'LEAK: org A resolved org B''s storage_prefix';
  -- A can see only its own prefix
  ASSERT (SELECT storage_prefix FROM documents) LIKE 'org/11111111-%',
    'org A should see only its own storage_prefix';
END $$;

RESET ROLE;
\echo 'RLS RED-TEAM PASSED — per-op × per-table isolation holds (read/insert/update/delete/fail-closed) incl. storage_prefix.'
