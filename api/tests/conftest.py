"""Shared test fixtures: an isolated in-memory DB session, and a real Mahsa subprocess for
integration tests."""

from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  registers all models on Base.metadata
from app.db.base import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mahsa_server() -> Iterator[str]:
    bin_path = REPO_ROOT / "dif" / "target" / "debug" / "mahsa"
    if not bin_path.exists():
        bin_path = REPO_ROOT / "dif" / "target" / "release" / "mahsa"
    if not bin_path.exists():
        pytest.skip(f"mahsa binary not built; run `cargo build` in {REPO_ROOT / 'dif'} first")

    port = _free_port()
    addr = f"127.0.0.1:{port}"
    proc = subprocess.Popen(
        [str(bin_path)],
        env={**os.environ, "MAHSA_ADDR": addr},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://{addr}"
    healthy = False
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=0.5) as r:
                if r.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(0.05)
    if not healthy:
        proc.terminate()
        pytest.fail("mahsa sidecar did not become healthy")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
