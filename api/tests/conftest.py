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
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Hermetic: tests must never depend on an ambient Mahsa (e.g. a dev sidecar on :8088). Point the
# default at a dead port before the app imports; tests needing a real engine use `mahsa_server`.
os.environ.setdefault("MAISHA_MAHSA_URL", "http://127.0.0.1:9")

import app.db.models  # noqa: E402,F401  registers all models on Base.metadata
from app.db.base import Base  # noqa: E402

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


@pytest.fixture(scope="module")
def betterauth_owner_env() -> Iterator[SimpleNamespace]:
    """P2-6 (hmac-retire): a real Ed25519 JWKS endpoint + a pre-minted OWNER JWT, module-scoped.

    The legacy shared-password login is deleted, so test files that drive ``app.main.app``
    through the ``_authenticate`` middleware (test_app / test_hardening / test_api_bulk) satisfy
    it the way production does: a Better Auth JWT, here carried in the ``maisha_jwt`` cookie
    (the HTMX path). Yields ``SimpleNamespace(base_url, kid, priv_pem, token)`` — ``token`` is a
    signed, in-date owner token (sub=u-owner, org=org-7); mint variants with ``priv_pem``/``kid``
    if a test needs a different identity. Per-instance unique ``kid`` + fresh port + jwks-client
    cache clears keep instances from poisoning each other (same discipline as test_auth_e2e.py).
    """
    import base64
    import json as _json
    import threading
    import uuid
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.core import betterauth

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    kid = f"conftest-kid-{uuid.uuid4()}"
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": base64.urlsafe_b64encode(pub).decode().rstrip("="),
        "kid": kid,
        "use": "sig",
        "alg": "EdDSA",
    }
    body = _json.dumps({"keys": [jwk]}).encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (stdlib method name)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "u-owner",
            "email": "owner@example.com",
            "iss": base_url,
            "aud": base_url,
            "iat": now,
            "exp": now + 3600,
            "activeOrganizationId": "org-7",
            "role": "owner",
        },
        priv_pem,
        algorithm="EdDSA",
        headers={"kid": kid},
    )

    mp = pytest.MonkeyPatch()
    betterauth._jwks_client.cache_clear()
    mp.setenv("MAISHA_BETTER_AUTH_URL", base_url)
    mp.delenv("MAISHA_BETTER_AUTH_ISSUER", raising=False)
    mp.delenv("MAISHA_BETTER_AUTH_AUDIENCE", raising=False)
    mp.delenv("MAISHA_BETTER_AUTH_MFA_CLAIM", raising=False)
    try:
        yield SimpleNamespace(base_url=base_url, kid=kid, priv_pem=priv_pem, token=token)
    finally:
        mp.undo()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        betterauth._jwks_client.cache_clear()
