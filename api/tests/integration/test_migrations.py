"""P1-MIGRATE: `alembic upgrade head` builds the full schema and leaves no model/DB drift."""

from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

import app.db.models  # noqa: F401  registers every model on Base.metadata
from alembic import command
from app.db.base import Base
from app.db.session import make_engine

API_ROOT = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_head_creates_every_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    command.upgrade(_config(url), "head")

    tables = set(inspect(make_engine(url)).get_table_names())
    expected = set(Base.metadata.tables)
    assert expected <= tables, f"missing tables after migrate: {expected - tables}"


def test_no_schema_drift_after_upgrade(tmp_path):
    """A fresh `revision --autogenerate` would be empty: models match the migrated DB."""
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    command.upgrade(_config(url), "head")

    engine = make_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diffs = compare_metadata(ctx, Base.metadata)
    assert diffs == [], f"unexpected schema drift: {diffs}"
