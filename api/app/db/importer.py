"""SQLite -> Postgres tenant importer (MASTER_PLAN §WS4.2).

Copies one tenant's existing single-tenant SQLite data (the pre-multi-tenancy app schema in
``app.db.models``) into the org-scoped ``tenant_core`` schema replayed onto Postgres by the
``0002_multitenant_core`` Alembic migration (source: ``infra/db/multitenant/``). Every imported
row is tagged with the caller-supplied ``org_id``/``entity_id`` — one importer run == one tenant.

Idempotent & retry-safe (UX research T8 flags a migration that silently double-imports or stalls
as a top competitor complaint): every target row's primary key is a UUID5 deterministically
derived from ``(org_id, table, source_pk)``, so re-running the same source against the same org
recomputes the SAME target ids and the insert is ``ON CONFLICT DO NOTHING`` — a second run
imports zero new rows and leaves the target unchanged.

Reconciliation is mandatory, not optional, and INDEPENDENT: :func:`reconcile` opens the SOURCE
database and the TARGET database separately and compares per-table row counts AND money-column
SUMS (integer paise) read fresh from each. It never looks at the rows the importer built in
memory — comparing the importer's output to the importer's output can only catch an arithmetic
slip inside the importer, never the dropped, failed or partially-committed insert that
reconciliation exists to detect. :func:`import_tenant` runs it after the import transaction
commits and returns the report; callers must check ``report.ok``, which is False the instant any
table disagrees.

ponytail: the target tables are declared here as a portable ``sqlalchemy.MetaData`` (generic
types, no native Postgres ``uuid``/RLS) purely so the round-trip is exercisable against a plain
SQLite double in tests without a live Postgres server. On Postgres this MetaData is NEVER used
to create anything (§0.8: it carries no RLS) — ``0002_multitenant_core`` owns those tables with
their policies, and the importer refuses to run if they are absent.
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.gst import GstReturn
from app.db.models.ledger import JournalEntry
from app.db.models.payables import Bill, Vendor
from app.db.models.payroll import Employee, SalaryStructure
from app.db.models.revenue import Customer, Invoice
from app.db.models.tax import TdsReturn
from app.db.models.treasury import BankAccount
from app.db.models.vault import Document
from app.db.session import make_engine

# Must match TENANT_SCHEMA in alembic/versions/0002_multitenant_core.py.
TENANT_SCHEMA = "tenant_core"


def _uuid5(*parts: str) -> str:
    """Deterministic target id from source identity. Re-running the importer recomputes the
    SAME id for the SAME source row, so ON CONFLICT DO NOTHING makes re-import a true no-op."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join(parts)))


def _build_target_tables(schema: str | None) -> tuple[MetaData, dict[str, Table]]:
    md = MetaData(schema=schema)
    tables: dict[str, Table] = {}

    def t(name: str, *cols) -> None:
        tables[name] = Table(name, md, *cols)

    t(
        "orgs",
        Column("id", String, primary_key=True),
        Column("name", String, nullable=False),
        Column("plan", String, nullable=False, default="basics"),
        Column("created_at", DateTime),
    )
    t(
        "entities",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("legal_name", String, nullable=False),
        Column("pan", String),
        Column("state_code", String),
        Column("created_at", DateTime),
    )
    t(
        "gstin_registrations",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("gstin", String, nullable=False),
        Column("state_code", String, nullable=False),
        Column("filing_profile", String, nullable=False, default="monthly"),
        Column("created_at", DateTime),
    )
    t(
        "vendors",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("name", String, nullable=False),
        Column("pan", String),
        Column("gstin", String),
        Column("created_at", DateTime),
    )
    t(
        "customers",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("name", String, nullable=False),
        Column("pan", String),
        Column("gstin", String),
        Column("created_at", DateTime),
    )
    t(
        "bank_accounts",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("account_number", String, nullable=False),
        Column("ifsc", String, nullable=False),
        Column("balance", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime),
    )
    t(
        "employees",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("name", String, nullable=False),
        Column("pan", String),
        Column("uan", String),
        Column("gross_salary", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime),
    )
    t(
        "tds_returns",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("form_type", String, nullable=False),
        Column("quarter", String, nullable=False),
        Column("total_tds", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime),
    )
    t(
        "documents",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("doc_type", String, nullable=False),
        Column("storage_prefix", String, nullable=False),
        Column("created_at", DateTime),
    )
    t(
        "bills",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("vendor_id", String),
        Column("bill_number", String, nullable=False),
        Column("bill_date", String, nullable=False),
        Column("subtotal", BigInteger, nullable=False),
        Column("tds_amount", BigInteger, nullable=False, default=0),
        Column("total_amount", BigInteger, nullable=False),
        Column("created_at", DateTime),
    )
    t(
        "invoices",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("gstin_registration_id", String),
        Column("invoice_number", String, nullable=False),
        Column("invoice_date", String, nullable=False),
        Column("taxable_value", BigInteger, nullable=False),
        Column("total_tax", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime),
    )
    t(
        "journal_entries",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("entity_id", String, nullable=False),
        Column("entry_date", String, nullable=False),
        Column("narration", String),
        Column("amount", BigInteger, nullable=False),
        Column("created_at", DateTime),
    )
    t(
        "gst_returns",
        Column("id", String, primary_key=True),
        Column("org_id", String, nullable=False),
        Column("gstin_registration_id", String),
        Column("return_type", String, nullable=False),
        Column("filing_period", String, nullable=False),
        Column("tax_payable", BigInteger, nullable=False, default=0),
        Column("late_fee", BigInteger, nullable=False, default=0),
        Column("interest", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime),
    )
    return md, tables


def _insert_ignore(conn: Connection, table: Table, rows: list[dict]) -> None:
    """Dialect-aware upsert-nothing: a row whose id already exists is left alone. This is the
    entire idempotency mechanism — no separate "already imported" ledger table needed."""
    if not rows:
        return
    dialect = conn.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        conn.execute(pg_insert(table).values(rows).on_conflict_do_nothing(index_elements=["id"]))
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        conn.execute(
            sqlite_insert(table).values(rows).on_conflict_do_nothing(index_elements=["id"])
        )
    else:  # pragma: no cover - only sqlite/postgres are supported targets
        raise NotImplementedError(f"unsupported target dialect: {dialect}")


@dataclass
class TableReport:
    table: str
    source_rows: int
    target_rows: int
    source_sums: dict[str, int]
    target_sums: dict[str, int]

    @property
    def ok(self) -> bool:
        return self.source_rows == self.target_rows and self.source_sums == self.target_sums


@dataclass
class ReconciliationReport:
    tables: list[TableReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tables)

    def render(self) -> str:
        header = f"{'table':<16}{'src_rows':>10}{'tgt_rows':>10}   money columns (paise)"
        lines = [header]
        for t in self.tables:
            status = "EQUAL" if t.ok else "NOT EQUAL"
            lines.append(f"{t.table:<16}{t.source_rows:>10}{t.target_rows:>10}   {status}")
            for col in t.source_sums:
                s, g = t.source_sums[col], t.target_sums.get(col)
                mark = "==" if s == g else "!="
                lines.append(f"    {col:<20} source={s} {mark} target={g}")
        lines.append("ALL EQUAL" if self.ok else "*** NOT EQUAL — DO NOT treat as complete ***")
        return "\n".join(lines)


# ---- independent reconciliation (source DB vs target DB, both read fresh) ---------------
#
# The whole point: NEITHER side may be derived from the in-memory rows the importer built.
# source stats come from a query against the SOURCE database's own (pre-multi-tenancy) tables;
# target stats come from a query against the TARGET database. Comparing the importer's output
# to the importer's output can only catch an arithmetic slip in the importer — never the
# dropped/failed/partial insert that reconciliation exists to detect.
#
# target table name -> (source model, {target money column: source expression})
_SOURCE_MAP: dict[str, tuple[type, dict[str, Any]]] = {
    "vendors": (Vendor, {}),
    "customers": (Customer, {}),
    "bank_accounts": (BankAccount, {"balance": BankAccount.current_balance}),
    "employees": (Employee, {}),  # gross_salary is not a source column — see _source_stats
    "tds_returns": (TdsReturn, {"total_tds": TdsReturn.total_deducted}),
    "documents": (Document, {}),
    "bills": (
        Bill,
        {
            "subtotal": Bill.subtotal,
            "tds_amount": Bill.tds_amount,
            "total_amount": Bill.total_amount,
        },
    ),
    "invoices": (
        Invoice,
        {
            "taxable_value": Invoice.subtotal,
            "total_tax": Invoice.igst_amount + Invoice.cgst_amount + Invoice.sgst_amount,
        },
    ),
    "journal_entries": (JournalEntry, {"amount": JournalEntry.total_debit}),
    "gst_returns": (
        GstReturn,
        {
            "tax_payable": GstReturn.tax_payable,
            "late_fee": GstReturn.late_fee,
            "interest": GstReturn.interest,
        },
    ),
}


def _source_employee_gross(src: Connection) -> int:
    """Sum of each employee's CURRENT gross salary, computed in SQL against the source DB.

    Deliberately a different algorithm from the importer's Python "sort by effective_from, last
    write wins" — a max()-per-employee join. Two implementations of the same rule disagreeing is
    exactly what reconciliation should surface.

    ponytail: two structures sharing the same max effective_from would be double-counted here and
    single-counted by the importer, so the report reads NOT EQUAL — fails closed, which is the
    correct direction for a migration. Deduplicate only if a real tenant hits it.
    """
    latest = (
        select(
            SalaryStructure.employee_id.label("employee_id"),
            func.max(SalaryStructure.effective_from).label("effective_from"),
        )
        .group_by(SalaryStructure.employee_id)
        .subquery()
    )
    stmt = (
        select(func.coalesce(func.sum(SalaryStructure.gross_salary), 0))
        .select_from(SalaryStructure.__table__)
        .join(
            latest,
            (SalaryStructure.employee_id == latest.c.employee_id)
            & (SalaryStructure.effective_from == latest.c.effective_from),
        )
        .where(SalaryStructure.employee_id.in_(select(Employee.id)))
    )
    return int(src.execute(stmt).scalar_one())


def _source_stats(src: Connection, target_table: str) -> tuple[int, dict[str, int]]:
    """Row count + money sums (integer paise) read straight from the SOURCE database."""
    model, money = _SOURCE_MAP[target_table]
    rows = int(
        src.execute(select(func.count()).select_from(model.__table__)).scalar_one()  # type: ignore[attr-defined]
    )
    sums = {
        col: int(src.execute(select(func.coalesce(func.sum(expr), 0))).scalar_one())
        for col, expr in money.items()
    }
    if target_table == "employees":
        sums["gross_salary"] = _source_employee_gross(src)
    return rows, sums


def _target_stats(
    tgt: Connection, table: Table, org_id: str, money_cols: tuple[str, ...]
) -> tuple[int, dict[str, int]]:
    """Row count + money sums read straight from the TARGET database, scoped to this org."""
    rows = int(
        tgt.execute(
            select(func.count()).select_from(table).where(table.c.org_id == org_id)
        ).scalar_one()
    )
    sums = {
        col: int(
            tgt.execute(
                select(func.coalesce(func.sum(table.c[col]), 0)).where(table.c.org_id == org_id)
            ).scalar_one()
        )
        for col in money_cols
    }
    return rows, sums


def reconcile(
    source_engine: Engine,
    target_engine: Engine,
    *,
    org_id: str,
    target_schema: str | None = None,
) -> ReconciliationReport:
    """Compare SOURCE and TARGET databases directly. Callable on its own, after any import, at
    any time — it holds no state from the import run and re-reads both databases."""
    _md, tables = _build_target_tables(target_schema)
    report = ReconciliationReport()
    with source_engine.connect() as src, target_engine.connect() as tgt:
        for name in _SOURCE_MAP:
            source_rows, source_sums = _source_stats(src, name)
            target_rows, target_sums = _target_stats(tgt, tables[name], org_id, tuple(source_sums))
            report.tables.append(
                TableReport(name, source_rows, target_rows, source_sums, target_sums)
            )
    return report


def _assert_postgres_target_migrated(
    present: set[str], required: set[str], schema: str | None
) -> None:
    """§0.8: the importer must NEVER create tenant tables on Postgres. ``create_all()`` builds
    them from the portable MetaData in this module, which has no RLS — a table created that way
    is readable across every org. ``0002_multitenant_core`` owns those tables together with their
    policies; if it has not run, refuse the import rather than silently produce unprotected ones.
    """
    missing = sorted(required - present)
    if missing:
        raise RuntimeError(
            f"target Postgres schema {schema!r} is missing tenant tables {missing}. "
            "Run `alembic upgrade head` first. The importer will not create them: "
            "create_all() would produce tables WITHOUT their RLS policies (§0.8)."
        )


def _prepare_target(
    conn: Connection, md: MetaData, tables: dict[str, Table], schema: str | None
) -> None:
    if conn.dialect.name == "postgresql":
        present = set(sa_inspect(conn).get_table_names(schema=schema))
        _assert_postgres_target_migrated(present, set(tables), schema)
        return
    # ponytail: SQLite target-double for tests only — no RLS engine exists there to omit.
    md.create_all(bind=conn, checkfirst=True)


def import_tenant(
    source_engine: Engine,
    target_engine: Engine,
    *,
    org_id: str,
    entity_id: str,
    org_name: str = "Imported Org",
    entity_name: str = "Imported Entity",
    gstin: str | None = None,
    target_schema: str | None = None,
) -> ReconciliationReport:
    """Import one tenant's SQLite data into ``org_id``/``entity_id`` in the target schema.
    Safe to call repeatedly: the second call imports zero rows and the report still reads
    EQUAL (see module docstring).

    ``gstin`` is REQUIRED when the source holds any ``gst_returns``: the target column
    ``gst_returns.gstin_registration_id`` is ``uuid NOT NULL`` (``002_domain_rls.sql``) and the
    pre-multi-tenancy source schema records no registration at all, so the operator must supply
    it. The importer will not invent one.
    """
    _md, tables = _build_target_tables(target_schema)

    src: Session = sessionmaker(bind=source_engine, future=True)()
    try:
        registration_id = _resolve_gstin_registration(src, org_id, gstin)
        with target_engine.begin() as conn:
            _prepare_target(conn, _md, tables, target_schema)
            now = datetime.now(UTC)
            _insert_ignore(
                conn,
                tables["orgs"],
                [{"id": org_id, "name": org_name, "plan": "basics", "created_at": now}],
            )
            _insert_ignore(
                conn,
                tables["entities"],
                [
                    {
                        "id": entity_id,
                        "org_id": org_id,
                        "legal_name": entity_name,
                        "pan": None,
                        "state_code": gstin[:2] if gstin else None,
                        "created_at": now,
                    }
                ],
            )
            if registration_id is not None:
                assert gstin is not None  # guaranteed by _resolve_gstin_registration
                _insert_ignore(
                    conn,
                    tables["gstin_registrations"],
                    [
                        {
                            "id": registration_id,
                            "org_id": org_id,
                            "entity_id": entity_id,
                            "gstin": gstin,
                            # First two characters of a GSTIN are the state code (GST
                            # registration numbering, CGST Rules r.10 / Form GST REG-06).
                            "state_code": gstin[:2],
                            "filing_profile": "monthly",
                            "created_at": now,
                        }
                    ],
                )

            _import_vendors(src, conn, tables, org_id, entity_id, now)
            _import_customers(src, conn, tables, org_id, entity_id, now)
            _import_bank_accounts(src, conn, tables, org_id, entity_id, now)
            _import_employees(src, conn, tables, org_id, entity_id, now)
            _import_tds_returns(src, conn, tables, org_id, entity_id, now)
            _import_documents(src, conn, tables, org_id, entity_id, now)
            _import_bills(src, conn, tables, org_id, entity_id, now)
            _import_invoices(src, conn, tables, org_id, entity_id, now, registration_id)
            _import_journal_entries(src, conn, tables, org_id, entity_id, now)
            _import_gst_returns(src, conn, tables, org_id, now, registration_id)
    finally:
        src.close()

    # Reconciliation runs AFTER the transaction commits, on fresh connections to both
    # databases, so it sees what actually landed — not what the importer meant to write.
    return reconcile(source_engine, target_engine, org_id=org_id, target_schema=target_schema)


def _resolve_gstin_registration(src: Session, org_id: str, gstin: str | None) -> str | None:
    """Deterministic registration id for ``gstin``, or None when the source has no GST returns.
    Raises when the source HAS returns but no GSTIN was supplied — see :func:`import_tenant`."""
    if gstin is not None:
        if len(gstin) != 15:
            raise ValueError(f"gstin must be 15 characters, got {len(gstin)}")
        return _uuid5(org_id, "gstin_registrations", gstin)
    count = src.execute(select(func.count()).select_from(GstReturn.__table__)).scalar_one()
    if count:
        raise ValueError(
            f"source holds {count} gst_returns but no gstin was supplied. Target column "
            "gst_returns.gstin_registration_id is uuid NOT NULL (infra/db/multitenant/"
            "002_domain_rls.sql) and the source schema records no registration — pass the "
            "tenant's GSTIN (--gstin). Refusing to invent one."
        )
    return None


# ---- per-table extraction (source ORM -> target row dicts) -----------------------------


def _import_vendors(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "vendors", str(v.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "name": v.name,
            "pan": v.pan,
            "gstin": v.gstin,
            "created_at": now,
        }
        for v in src.execute(select(Vendor)).scalars().all()
    ]
    _insert_ignore(conn, tables["vendors"], rows)


def _import_customers(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "customers", str(c.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "name": c.name,
            "pan": c.pan,
            "gstin": c.gstin,
            "created_at": now,
        }
        for c in src.execute(select(Customer)).scalars().all()
    ]
    _insert_ignore(conn, tables["customers"], rows)


def _import_bank_accounts(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "bank_accounts", str(b.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "account_number": b.account_number,
            "ifsc": b.ifsc,
            "balance": b.current_balance,
            "created_at": now,
        }
        for b in src.execute(select(BankAccount)).scalars().all()
    ]
    _insert_ignore(conn, tables["bank_accounts"], rows)


def _import_employees(src, conn, tables, org_id, entity_id, now) -> None:
    latest_gross: dict[int, int] = {}
    salaries = src.execute(select(SalaryStructure)).scalars().all()
    for s in sorted(salaries, key=lambda s: s.effective_from):
        latest_gross[s.employee_id] = s.gross_salary  # last write wins = most recent structure

    rows = [
        {
            "id": _uuid5(org_id, "employees", str(e.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "name": e.name,
            "pan": e.pan,
            "uan": e.uan,
            "gross_salary": latest_gross.get(e.id, 0),
            "created_at": now,
        }
        for e in src.execute(select(Employee)).scalars().all()
    ]
    _insert_ignore(conn, tables["employees"], rows)


def _import_tds_returns(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "tds_returns", str(r.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "form_type": r.return_type,
            "quarter": r.quarter,
            "total_tds": r.total_deducted,
            "created_at": now,
        }
        for r in src.execute(select(TdsReturn)).scalars().all()
    ]
    _insert_ignore(conn, tables["tds_returns"], rows)


def _import_documents(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "documents", d.id),
            "org_id": org_id,
            "entity_id": entity_id,
            "doc_type": d.doc_type,
            "storage_prefix": d.file_path,
            "created_at": now,
        }
        for d in src.execute(select(Document)).scalars().all()
    ]
    _insert_ignore(conn, tables["documents"], rows)


def _import_bills(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "bills", str(b.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "vendor_id": _uuid5(org_id, "vendors", str(b.vendor_id)),
            "bill_number": b.bill_number,
            "bill_date": b.bill_date,
            "subtotal": b.subtotal,
            "tds_amount": b.tds_amount,
            "total_amount": b.total_amount,
            "created_at": now,
        }
        for b in src.execute(select(Bill)).scalars().all()
    ]
    _insert_ignore(conn, tables["bills"], rows)


def _import_invoices(src, conn, tables, org_id, entity_id, now, registration_id) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "invoices", str(i.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "gstin_registration_id": registration_id,
            "invoice_number": i.invoice_number,
            "invoice_date": i.invoice_date,
            "taxable_value": i.subtotal,
            "total_tax": i.igst_amount + i.cgst_amount + i.sgst_amount,
            "created_at": now,
        }
        for i in src.execute(select(Invoice)).scalars().all()
    ]
    _insert_ignore(conn, tables["invoices"], rows)


def _import_journal_entries(src, conn, tables, org_id, entity_id, now) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "journal_entries", str(j.id)),
            "org_id": org_id,
            "entity_id": entity_id,
            "entry_date": j.entry_date,
            "narration": j.description,
            "amount": j.total_debit,
            "created_at": now,
        }
        for j in src.execute(select(JournalEntry)).scalars().all()
    ]
    _insert_ignore(conn, tables["journal_entries"], rows)


def _import_gst_returns(src, conn, tables, org_id, now, registration_id) -> None:
    rows = [
        {
            "id": _uuid5(org_id, "gst_returns", str(g.id)),
            "org_id": org_id,
            "gstin_registration_id": registration_id,
            "return_type": g.return_type,
            "filing_period": g.filing_period,
            "tax_payable": g.tax_payable,
            "late_fee": g.late_fee,
            "interest": g.interest,
            "created_at": now,
        }
        for g in src.execute(select(GstReturn)).scalars().all()
    ]
    _insert_ignore(conn, tables["gst_returns"], rows)


# ---- CLI (ops use: `python -m app.db.importer ...`) -------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True, help="source SQLite database URL")
    parser.add_argument("--target-url", required=True, help="target Postgres database URL")
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--org-name", default="Imported Org")
    parser.add_argument("--entity-name", default="Imported Entity")
    parser.add_argument(
        "--gstin",
        help="tenant GSTIN (15 chars); REQUIRED if the source holds any gst_returns, because "
        "tenant_core.gst_returns.gstin_registration_id is NOT NULL and the source schema "
        "records no registration",
    )
    args = parser.parse_args()

    source_engine = make_engine(args.source_url)
    target_engine = make_engine(args.target_url)
    schema = TENANT_SCHEMA if target_engine.dialect.name == "postgresql" else None
    report = import_tenant(
        source_engine,
        target_engine,
        org_id=args.org_id,
        entity_id=args.entity_id,
        org_name=args.org_name,
        entity_name=args.entity_name,
        gstin=args.gstin,
        target_schema=schema,
    )
    print(report.render())
    if not report.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
