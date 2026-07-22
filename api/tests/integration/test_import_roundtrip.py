"""WS4.2 — migration engineering tests.

1. SQLite -> SQLite round-trip: proves the importer's reconciliation (row counts + per-table
   money-column paise sums, read INDEPENDENTLY from the source DB and the target DB) and its
   idempotency (a second run changes nothing), end to end, using a SQLite database as the
   target-double (see importer.py module docstring for why this exercises the identical code
   path Postgres would run). The reconciliation is then proven non-vacuous by damaging a real
   imported target — a dropped row and a silently altered paise amount — and by moving the
   SOURCE out from under a clean import.
2. SQLite -> Postgres: same assertions against a REAL Postgres, explicitly skipped with a
   `reason=` when unavailable (never a silent skip) — this environment has neither `psycopg2`
   nor a Postgres server.
3. WS1.C5-migration: the Alembic data migration that recomputes vault retention_until from
   7y-stale to the correct 8y-from-FY-end value, and leaves already-correct rows untouched.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

import app.db.models  # noqa: F401  registers every model on Base.metadata
from alembic import command
from app.db.base import Base
from app.db.importer import (
    _assert_postgres_target_migrated,
    _build_target_tables,
    import_tenant,
    reconcile,
)
from app.db.models.payables import Bill, Vendor
from app.db.models.payroll import Employee, SalaryStructure
from app.db.models.revenue import Customer, Invoice
from app.db.models.tax import TdsReturn
from app.db.models.treasury import BankAccount
from app.db.models.vault import Document
from app.db.session import make_engine, make_session_factory
from app.domains.vault import vault_calc

API_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_source(session_factory) -> None:
    """A small but representative slice across every table the importer touches, including
    one intentional multi-structure employee (latest salary must win)."""
    with session_factory() as s:
        s.add(Vendor(id=1, name="Acme Supplies", pan="ABCDE1234F", gstin="27ABCDE1234F1Z5"))
        s.add(Customer(id=1, name="Beta Corp", pan="BBCDE1234F", gstin="29BBCDE1234F1Z5"))
        s.add(
            BankAccount(
                id=1,
                bank_name="HDFC",
                account_number="000123456789",
                ifsc="HDFC0000001",
                opening_balance=10_00_000,
                current_balance=12_50_000,
            )
        )
        s.add(
            Employee(
                id=1,
                employee_code="E001",
                name="Priya Rao",
                date_of_joining="2024-01-01",
            )
        )
        s.add(
            SalaryStructure(
                id=1,
                employee_id=1,
                effective_from="2024-01-01",
                basic=40_000_00,
                hra=20_000_00,
                employer_pf=4_800_00,
                employee_pf=4_800_00,
                gross_salary=60_000_00,
                net_salary=55_200_00,
                ctc=64_800_00,
            )
        )
        s.add(
            SalaryStructure(
                id=2,
                employee_id=1,
                effective_from="2025-04-01",  # later -> importer must pick THIS gross_salary
                basic=50_000_00,
                hra=25_000_00,
                employer_pf=6_000_00,
                employee_pf=6_000_00,
                gross_salary=75_000_00,
                net_salary=69_000_00,
                ctc=81_000_00,
            )
        )
        s.add(
            TdsReturn(
                id=1,
                return_type="26Q",
                quarter="2026-Q1",
                due_date="2026-05-31",
                total_deducted=1_50_000_00,
            )
        )
        s.add(
            Document(
                id="a" * 64,
                file_name="invoice.pdf",
                file_path="vault/aaaa",
                doc_type="invoice",
                upload_date="2026-01-15",
                retention_until=vault_calc.retention_until("2026-01-15", "invoice"),
                sha256="a" * 64,
            )
        )
        s.flush()  # vendor/customer rows must exist before bill/invoice FKs reference them
        s.add(
            Bill(
                id=1,
                bill_number="BILL-001",
                vendor_id=1,
                bill_date="2026-06-01",
                due_date="2026-06-30",
                subtotal=1_00_000_00,
                tds_amount=1_000_00,
                total_amount=1_18_000_00,
            )
        )
        s.add(
            Invoice(
                id=1,
                invoice_number="INV-001",
                customer_id=1,
                invoice_date="2026-06-05",
                due_date="2026-07-05",
                subtotal=2_00_000_00,
                igst_amount=0,
                cgst_amount=18_000_00,
                sgst_amount=18_000_00,
                total_amount=2_36_000_00,
                net_receivable=2_36_000_00,
            )
        )
        from app.db.models.gst import GstReturn
        from app.db.models.ledger import JournalEntry

        s.add(
            JournalEntry(
                id=1,
                entry_date="2026-06-30",
                description="June revenue recognition",
                total_debit=2_36_000_00,
                total_credit=2_36_000_00,
            )
        )
        s.add(
            GstReturn(
                id=1,
                return_type="GSTR-3B",
                filing_period="2026-06",
                due_date="2026-07-20",
                tax_payable=36_000_00,
                late_fee=0,
                interest=0,
            )
        )
        s.commit()


ORG_ID = "org-1"
ENTITY_ID = "entity-1"
GSTIN = "27ABCDE1234F1Z5"  # source seed holds gst_returns -> a registration is mandatory


def _make_source(tmp_path):
    source_engine = make_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(bind=source_engine)
    _seed_source(make_session_factory(source_engine))
    return source_engine


def _run_import(tmp_path, target_url: str, target_schema: str | None = None):
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(target_url)
    kwargs = dict(org_id=ORG_ID, entity_id=ENTITY_ID, gstin=GSTIN, target_schema=target_schema)
    report1 = import_tenant(source_engine, target_engine, **kwargs)
    report2 = import_tenant(source_engine, target_engine, **kwargs)  # idempotency: re-run
    return report1, report2


def test_sqlite_round_trip_reconciles_and_is_idempotent(tmp_path):
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    report1, report2 = _run_import(tmp_path, target_url)

    assert report1.tables, "importer produced no table reports"
    for t in report1.tables:
        assert t.ok, f"{t.table}: source/target mismatch on first import\n{report1.render()}"

    # idempotency: identical row counts and sums on the second pass — nothing double-imported.
    by_name1 = {t.table: t for t in report1.tables}
    for t in report2.tables:
        assert t.ok, f"{t.table}: NOT EQUAL on re-run\n{report2.render()}"
        assert t.target_rows == by_name1[t.table].target_rows, (
            f"{t.table}: row count changed on re-run "
            f"({by_name1[t.table].target_rows} -> {t.target_rows}) — importer is not idempotent"
        )


def _corrupt_and_reconcile(tmp_path, statement: str):
    """Run a REAL import, damage the TARGET database behind the importer's back, then run
    reconciliation again. The importer's in-memory rows are long gone, so a report that still
    reads EQUAL proves the reconciliation never opened the databases."""
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(f"sqlite:///{tmp_path / 'target_mut.db'}")
    clean = import_tenant(
        source_engine, target_engine, org_id=ORG_ID, entity_id=ENTITY_ID, gstin=GSTIN
    )
    assert clean.ok, f"import was not clean before corruption\n{clean.render()}"

    with target_engine.begin() as conn:
        assert conn.execute(text(statement)).rowcount == 1, "corruption statement hit no row"

    after = reconcile(source_engine, target_engine, org_id=ORG_ID)
    return {t.table: t for t in after.tables}, after


def test_reconciliation_detects_a_row_lost_from_the_target(tmp_path):
    """A dropped row is the exact data loss reconciliation exists to catch."""
    by_name, report = _corrupt_and_reconcile(tmp_path, "DELETE FROM bills WHERE org_id = 'org-1'")
    assert not report.ok, f"lost row went undetected\n{report.render()}"
    bills = by_name["bills"]
    assert bills.source_rows == 1 and bills.target_rows == 0
    assert not bills.ok
    assert "NOT EQUAL" in report.render()
    # untouched tables must still read EQUAL — the report localises the damage
    assert by_name["invoices"].ok and by_name["employees"].ok


def test_reconciliation_detects_a_money_column_silently_altered(tmp_path):
    """Row counts alone are not enough: a corrupted amount keeps the count identical."""
    by_name, report = _corrupt_and_reconcile(
        tmp_path, "UPDATE invoices SET total_tax = total_tax - 1 WHERE org_id = 'org-1'"
    )
    assert not report.ok, f"altered paise went undetected\n{report.render()}"
    inv = by_name["invoices"]
    assert inv.source_rows == inv.target_rows == 1, "row counts must be identical here"
    assert inv.source_sums["total_tax"] == inv.target_sums["total_tax"] + 1
    assert not inv.ok


def test_reconciliation_reads_the_source_database_not_the_importer_output(tmp_path):
    """Change the SOURCE after a clean import: reconciliation must now disagree. If it were
    still summing the importer's own rows it would have no way to notice."""
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(f"sqlite:///{tmp_path / 'target_src.db'}")
    assert import_tenant(
        source_engine, target_engine, org_id=ORG_ID, entity_id=ENTITY_ID, gstin=GSTIN
    ).ok

    with source_engine.begin() as conn:
        conn.execute(text("UPDATE bank_accounts SET current_balance = current_balance + 5000"))

    report = reconcile(source_engine, target_engine, org_id=ORG_ID)
    bank = {t.table: t for t in report.tables}["bank_accounts"]
    assert not report.ok
    assert bank.source_sums["balance"] == bank.target_sums["balance"] + 5000


def test_reconciliation_is_scoped_to_this_org(tmp_path):
    """Another org's rows in the same target must not be counted as this org's."""
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(f"sqlite:///{tmp_path / 'target_two.db'}")
    assert import_tenant(
        source_engine, target_engine, org_id=ORG_ID, entity_id=ENTITY_ID, gstin=GSTIN
    ).ok
    assert import_tenant(
        source_engine,
        target_engine,
        org_id="org-2",
        entity_id="entity-2",
        gstin="29ABCDE1234F1Z5",
    ).ok
    assert reconcile(source_engine, target_engine, org_id=ORG_ID).ok
    assert reconcile(source_engine, target_engine, org_id="org-2").ok
    # a third org imported nothing: every table must read 0 target rows against a non-empty
    # source, i.e. NOT ok. (A cross-org sum would make this read EQUAL.)
    empty = reconcile(source_engine, target_engine, org_id="org-3")
    assert not empty.ok
    assert all(t.target_rows == 0 for t in empty.tables)


def test_gst_returns_import_requires_a_gstin(tmp_path):
    """tenant_core.gst_returns.gstin_registration_id is uuid NOT NULL — the source schema has
    no registration, so the importer must refuse rather than write NULL (which Postgres would
    reject mid-migration, leaving a partial import)."""
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(f"sqlite:///{tmp_path / 'target_nogstin.db'}")
    with pytest.raises(ValueError, match="gst_returns"):
        import_tenant(source_engine, target_engine, org_id=ORG_ID, entity_id=ENTITY_ID)


def test_gst_returns_carry_a_real_registration_id(tmp_path):
    source_engine = _make_source(tmp_path)
    target_engine = make_engine(f"sqlite:///{tmp_path / 'target_gstin.db'}")
    assert import_tenant(
        source_engine, target_engine, org_id=ORG_ID, entity_id=ENTITY_ID, gstin=GSTIN
    ).ok
    with target_engine.connect() as conn:
        reg = conn.execute(
            text("SELECT id, gstin, state_code FROM gstin_registrations WHERE org_id = 'org-1'")
        ).one()
        null_regs = conn.execute(
            text("SELECT count(*) FROM gst_returns WHERE gstin_registration_id IS NULL")
        ).scalar_one()
        linked = conn.execute(text("SELECT gstin_registration_id FROM gst_returns")).scalars().all()
    assert reg.gstin == GSTIN
    assert reg.state_code == "27"  # first two chars of a GSTIN are the state code
    assert null_regs == 0, "a NOT NULL column would have failed the Postgres import"
    assert linked == [reg.id]


def test_importer_refuses_to_create_tenant_tables_on_postgres(tmp_path):
    """§0.8: create_all() from this module's portable MetaData would produce tenant tables with
    NO RLS policy — readable across every org. On Postgres the importer must refuse instead."""
    _md, tables = _build_target_tables("tenant_core")
    required = set(tables)

    # migration has run: all tables present -> proceeds
    _assert_postgres_target_migrated(required, required, "tenant_core")

    # migration has NOT run for one table -> refuses, and names it
    with pytest.raises(RuntimeError, match="bills"):
        _assert_postgres_target_migrated(required - {"bills"}, required, "tenant_core")


def test_migration_0002_inlines_its_sql_and_every_table_has_rls(tmp_path):
    """The revision must not resolve its content from the filesystem at runtime (an immutable
    revision cannot glob), and every tenant table it creates must ship RLS + a policy in the
    SAME migration (§0.8) — the check_rls_coverage.sh gate only greps infra/, so the Alembic
    path needs its own proof."""
    rev_path = API_ROOT / "alembic" / "versions" / "0002_multitenant_core.py"
    tree = ast.parse(rev_path.read_text())

    # (a) the revision may import nothing that can reach the filesystem.
    imported = {
        n.module.split(".")[0]
        if isinstance(n, ast.ImportFrom) and n.module
        else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [None])  # type: ignore[list-item]
    }
    assert imported <= {"__future__", "alembic"}, (
        f"revision 0002 imports {sorted(imported - {'__future__', 'alembic'})}; an immutable "
        "revision must carry its SQL inline, not reach out for it"
    )

    # (b) no call anywhere named glob/read_text/open/iterdir.
    called = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    }
    assert not called & {"glob", "read_text", "open", "iterdir", "read_bytes"}, (
        f"revision 0002 resolves its content at runtime via {sorted(called)}"
    )

    spec = importlib.util.spec_from_file_location("rev0002", rev_path)
    assert spec and spec.loader
    rev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rev)
    sql = "\n".join(rev.SCHEMA_SQL)

    # global-identity tables, matching the allow-list in scripts/check_rls_coverage.sh
    allowed = {"app_users", "password_credentials", "mfa_totp"}
    created = set(re.findall(r"CREATE TABLE ([a-z_]+)", sql)) - allowed
    assert len(created) >= 15, f"expected the full tenant schema, found {sorted(created)}"
    for table in sorted(created):
        assert re.search(rf"ALTER TABLE {table}\s+ENABLE ROW LEVEL SECURITY", sql), (
            f"{table} is created by revision 0002 without ENABLE ROW LEVEL SECURITY (§0.8)"
        )
        assert re.search(rf"CREATE POLICY [a-z_]+ ON {table}\b", sql), (
            f"{table} is created by revision 0002 without an RLS policy (§0.8)"
        )


def test_postgres_round_trip_reconciles(tmp_path):
    pytest.importorskip(
        "psycopg2",
        reason="psycopg2 not installed in this environment — Postgres round-trip cannot run; "
        "the identical importer code path is proven against a SQLite target-double in "
        "test_sqlite_round_trip_reconciles_and_is_idempotent",
    )
    pg_url = os.environ.get("MAISHA_TEST_POSTGRES_URL")
    if not pg_url:
        pytest.skip(
            reason="MAISHA_TEST_POSTGRES_URL not set and no live Postgres server is reachable "
            "in this environment — Postgres round-trip cannot run here"
        )
    command.upgrade(_alembic_config(pg_url), "head")
    report1, report2 = _run_import(tmp_path, pg_url, target_schema="tenant_core")
    for t in report1.tables:
        assert t.ok, f"{t.table}: source/target mismatch on first import\n{report1.render()}"
    for t in report2.tables:
        assert t.ok, f"{t.table}: NOT EQUAL on re-run\n{report2.render()}"


# ---- WS1.C5-migration: vault retention_until 7y -> 8y backfill -------------------------


def test_vault_retention_migration_recomputes_stale_7y_rows(tmp_path):
    url = f"sqlite:///{tmp_path / 'retention.db'}"
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0001_baseline")

    engine = make_engine(url)
    factory = make_session_factory(engine)
    stale_correct_8y = vault_calc.retention_until("2020-05-10", "invoice")
    stale_7y = date(date.fromisoformat(stale_correct_8y).year - 1, 3, 31).isoformat()
    already_correct = vault_calc.retention_until("2025-02-01", "invoice")

    with factory() as s:
        s.add(
            Document(
                id="s" * 64,
                file_name="old_invoice.pdf",
                file_path="vault/stale",
                doc_type="invoice",
                upload_date="2020-05-10",
                retention_until=stale_7y,  # the old, wrong 7y-from-FY-end value
                sha256="s" * 64,
            )
        )
        s.add(
            Document(
                id="c" * 64,
                file_name="already_correct.pdf",
                file_path="vault/correct",
                doc_type="invoice",
                upload_date="2025-02-01",
                retention_until=already_correct,  # already the right 8y value
                sha256="c" * 64,
            )
        )
        s.add(
            Document(
                id="p" * 64,
                file_name="cap_table.pdf",
                file_path="vault/permanent",
                doc_type="cap_table",
                upload_date="2025-02-01",
                retention_until=None,  # permanent — must stay None
                sha256="p" * 64,
            )
        )
        s.commit()

    command.upgrade(cfg, "head")

    with factory() as s:
        stale = s.get(Document, "s" * 64)
        correct = s.get(Document, "c" * 64)
        permanent = s.get(Document, "p" * 64)

    assert stale.retention_until == stale_correct_8y
    assert stale.retention_until != stale_7y
    assert correct.retention_until == already_correct  # untouched, still correct
    assert permanent.retention_until is None  # permanent class unaffected
