"""Alembic environment — schema versioning (P1-MIGRATE).

URL and metadata come from the app itself, so migrations always target the configured
database and the real models. ponytail: the baseline migration delegates to
``Base.metadata.create_all``; generate per-change deltas with
``alembic revision --autogenerate`` from here on.
"""

from __future__ import annotations

import app.db.models  # noqa: F401  registers every model on Base.metadata
from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.session import make_engine

target_metadata = Base.metadata


def _url() -> str:
    # tests pass an explicit url; production falls back to the app settings.
    return context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
