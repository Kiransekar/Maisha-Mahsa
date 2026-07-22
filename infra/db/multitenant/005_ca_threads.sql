-- MMX-1.0 §WS8.2 — CA query threads pinned to entries (raise -> respond-with-doc -> resolve).
--
-- TENANT-SCOPED. A thread and its events are facts about one org's books, so both tables carry
-- org_id and get the standard RLS treatment used by 001/002/003/004: policy keyed on
-- app_current_org(), the session GUC the app sets from the VERIFIED JWT claim — never a request
-- body (§0.8). No org bound -> app_current_org() IS NULL -> zero rows (fail closed).
--
-- Tamper-evidence does NOT live here: every raise/respond/resolve is ALSO sealed onto the
-- hash-chained audit_log (app.core.ca_threads.thread_event_payload); these tables are the
-- queryable mirror. Grants enforce the write discipline: ca_thread_event is append-only
-- (SELECT/INSERT, never UPDATE/DELETE); ca_thread allows UPDATE of the state column ONLY —
-- the pinned entry, question and author can never be rewritten even by an app bug.

CREATE TABLE ca_thread (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  domain      text NOT NULL,
  entry_ref   text NOT NULL,
  question    text NOT NULL,
  state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'responded', 'resolved')),
  raised_by   uuid NOT NULL REFERENCES app_users(id)
);
CREATE INDEX ca_thread_lookup ON ca_thread(org_id, state);

ALTER TABLE ca_thread ENABLE ROW LEVEL SECURITY;
ALTER TABLE ca_thread FORCE  ROW LEVEL SECURITY;
CREATE POLICY ca_thread_tenant ON ca_thread
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON ca_thread TO maisha_app;
GRANT UPDATE (state) ON ca_thread TO maisha_app;

CREATE TABLE ca_thread_event (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  thread_id   uuid NOT NULL REFERENCES ca_thread(id) ON DELETE CASCADE,
  timestamp   timestamptz NOT NULL DEFAULT now(),
  event       text NOT NULL CHECK (event IN ('raise', 'respond', 'resolve')),
  user_id     uuid NOT NULL REFERENCES app_users(id),
  note        text,
  doc_id      text,          -- vault documents.id (content sha256) — respond-with-doc evidence
  audit_hash  text           -- audit_log.this_hash of the sealed chain entry for this event
);
CREATE INDEX ca_thread_event_lookup ON ca_thread_event(org_id, thread_id);

ALTER TABLE ca_thread_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE ca_thread_event FORCE  ROW LEVEL SECURITY;
CREATE POLICY ca_thread_event_tenant ON ca_thread_event
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON ca_thread_event TO maisha_app;
