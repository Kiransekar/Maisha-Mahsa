"""WS10.4 — legal_acceptance table + its RLS policy, in this same revision (§0.8).

``legal_acceptance`` previously existed ONLY as a SQLAlchemy model: no migration, therefore no
table in ``tenant_core``, no RLS policy, and invisible to ``scripts/check_rls_coverage.sh``. It
holds ``user_id`` and is tenant data, so it ships here with ``org_id`` and a policy keyed on
``app_current_org()`` — the session GUC the app sets from the VERIFIED JWT claim, never a
request body.

The SQL is INLINED, not read from disk, for the reason ``0002_multitenant_core`` documents at
length: a migration's content must be immutable, so editing ``infra/db/multitenant/004_legal.sql``
must never silently change what this revision "was". That file stays the reviewable/red-team
source and the input to the RLS coverage gate; the block below is a verbatim snapshot of it as
of this revision. Any later change is a NEW revision.

The companion ``legal_document`` table is intentionally NOT created — the registry of published
versions moved into code (``app.core.legal.PUBLISHED``); see that module.

No-op on SQLite (dev/test): RLS, roles and ``gen_random_uuid()`` are Postgres-only, matching
0002.

Revision ID: 0004_legal_acceptance
Revises: 0003_vault_retention_8y
Create Date: 2026-07-21
"""

# ruff: noqa: E501 — the SQL below is a verbatim snapshot; reflowing it would break the
# byte-for-byte correspondence with infra/db/multitenant/004_legal.sql that makes it reviewable.
from __future__ import annotations

from alembic import op

revision = "0004_legal_acceptance"
down_revision = "0003_vault_retention_8y"
branch_labels = None
depends_on = None

TENANT_SCHEMA = "tenant_core"


# ---- snapshot of infra/db/multitenant/004_legal.sql --------------------------------------
_004_SQL = """
-- MMX-1.0 §WS10.4 — legal kit: append-only acceptance log.
--
-- TENANT-SCOPED. An acceptance is a fact about a customer org (its user bound the org to a
-- ToS/Privacy/DPA version), so the row carries org_id and gets the standard RLS treatment used
-- by every other tenant-scoped table in 001/002/003: policy keyed on app_current_org(), which
-- reads the session GUC the app sets from the VERIFIED JWT claim — never a request body (§0.8).
-- With no org bound, app_current_org() is NULL and this policy matches zero rows (fail closed).
--
-- There is deliberately NO legal_document table: the set of published versions points at files
-- in docs/legal/ that only a deploy can change, so it lives in code (app.core.legal.PUBLISHED),
-- not in the tenant schema. See that module's docstring.
--
-- Append-only is enforced by the GRANT, not by convention: the app role gets SELECT and INSERT
-- and is never granted UPDATE or DELETE, so the evidence cannot be rewritten by the application
-- even with a bug or an injected statement. Corrections are new rows.

CREATE TABLE legal_acceptance (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id      uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  doc_type     text NOT NULL CHECK (doc_type IN ('tos', 'privacy', 'dpa')),
  version      text NOT NULL,
  accepted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX legal_acceptance_lookup ON legal_acceptance(org_id, user_id, doc_type);

ALTER TABLE legal_acceptance ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_acceptance FORCE  ROW LEVEL SECURITY;
CREATE POLICY legal_acceptance_tenant ON legal_acceptance
  USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org());

GRANT SELECT, INSERT ON legal_acceptance TO maisha_app;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # ponytail: sqlite dev/test has no RLS/roles/uuid-gen — nothing to replay
    op.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
    op.execute(_004_SQL)
    op.execute("SET search_path TO public")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"DROP TABLE IF EXISTS {TENANT_SCHEMA}.legal_acceptance")
