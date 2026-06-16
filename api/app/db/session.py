"""Engine + session factory. SQLite with foreign keys enforced (off by default in SQLite)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

_IN_MEMORY = ("sqlite://", "sqlite:///:memory:")


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    # For a file-backed SQLite URL, ensure the parent directory exists.
    if url.startswith("sqlite:///") and ":memory:" not in url:
        from pathlib import Path

        db_path = url.removeprefix("sqlite:///")
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        # In-memory SQLite must share one connection or each session sees an empty DB.
        if url in _IN_MEMORY:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def session_factory() -> sessionmaker[Session]:
    global _engine, _factory
    if _factory is None:
        _engine = make_engine()
        _factory = make_session_factory(_engine)
    return _factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yield a session and always close it."""
    factory = session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
