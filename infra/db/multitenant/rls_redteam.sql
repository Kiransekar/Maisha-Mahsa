-- MMX-1.0 §WS4.1/§WS4.7 seed — prove RLS isolates tenants. Seeds two orgs as the privileged
-- owner, then drops to the non-superuser app role and asserts an authenticated session for org A
-- can never read, write, or reach org B's rows. Any ASSERT/RAISE failure exits psql non-zero.
\set ON_ERROR_STOP on

-- provisioning is privileged (owner bypasses RLS) — this is the only place rows cross org lines.
INSERT INTO orgs (id, name) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Org A'),
  ('22222222-2222-2222-2222-222222222222', 'Org B');
INSERT INTO entities (id, org_id, legal_name) VALUES
  ('a1111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'A Ltd'),
  ('b2222222-2222-2222-2222-222222222222', '22222222-2222-2222-2222-222222222222', 'B Ltd');
INSERT INTO bills (org_id, entity_id, bill_number, bill_date, subtotal, total_amount) VALUES
  ('11111111-1111-1111-1111-111111111111', 'a1111111-1111-1111-1111-111111111111', 'A-1', '2026-04-01', 100000, 100000),
  ('22222222-2222-2222-2222-222222222222', 'b2222222-2222-2222-2222-222222222222', 'B-1', '2026-04-01', 200000, 200000);

-- everything below runs as the application role, subject to RLS.
SET ROLE maisha_app;

-- (1) org A sees only its own bill.
SET app.current_org = '11111111-1111-1111-1111-111111111111';
DO $$ BEGIN
  ASSERT (SELECT count(*) FROM bills) = 1, 'org A must see exactly 1 bill';
  ASSERT (SELECT bill_number FROM bills LIMIT 1) = 'A-1', 'org A leaked B-1';
END $$;

-- (2) org B sees only its own bill.
SET app.current_org = '22222222-2222-2222-2222-222222222222';
DO $$ BEGIN
  ASSERT (SELECT count(*) FROM bills) = 1, 'org B must see exactly 1 bill';
  ASSERT (SELECT bill_number FROM bills LIMIT 1) = 'B-1', 'org B leaked A-1';
END $$;

-- (3) a cross-org WRITE (org A session inserting a row tagged org B) is rejected.
SET app.current_org = '11111111-1111-1111-1111-111111111111';
DO $$
DECLARE blocked boolean := false;
BEGIN
  BEGIN
    INSERT INTO bills (org_id, entity_id, bill_number, bill_date, subtotal, total_amount)
      VALUES ('22222222-2222-2222-2222-222222222222',
              'b2222222-2222-2222-2222-222222222222', 'X-1', '2026-04-01', 1, 1);
  EXCEPTION WHEN others THEN
    blocked := true;   -- RLS WITH CHECK (or the invisible-FK) rejected it
  END;
  ASSERT blocked, 'cross-org INSERT must be blocked by RLS';
END $$;

-- (4) a cross-org UPDATE touches nothing (B's row is invisible to A).
SET app.current_org = '11111111-1111-1111-1111-111111111111';
DO $$
DECLARE n integer;
BEGIN
  UPDATE bills SET subtotal = 0 WHERE bill_number = 'B-1';
  GET DIAGNOSTICS n = ROW_COUNT;
  ASSERT n = 0, 'org A must not be able to UPDATE org B rows';
END $$;

-- (5) fail-closed: with no org bound, the session sees nothing.
RESET app.current_org;
DO $$ BEGIN
  ASSERT (SELECT count(*) FROM bills) = 0, 'unbound session must see 0 rows (fail-closed)';
END $$;

RESET ROLE;
\echo 'RLS RED-TEAM PASSED — tenant isolation holds for read, write, update, and fail-closed.'
