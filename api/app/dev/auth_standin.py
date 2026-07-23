"""Dev/demo auth stand-in — a JWKS issuer + one-click sign-in, for TEST deployments only.

The real product verifies Better Auth's JWTs via JWKS and never mints them (see
``app.core.betterauth`` — Better Auth is the owner's external Node service). That is correct for
production but makes a throwaway *demo* deploy impossible: there is nobody to hand out a token, so
every route 401s and you can never see the app.

This module is the sanctioned stand-in — the exact shape ``frontend/e2e/stack.mjs`` and
``api/tests/conftest.py`` already use, ported to Python so a single container can host it:

  * :data:`jwks_app` — a minimal ASGI app serving ``GET /api/auth/jwks`` (the public Ed25519 key).
    Run it as its OWN process (``uvicorn app.dev.auth_standin:jwks_app``) on a private port so the
    API's blocking ``PyJWKClient`` fetch never contends with the API's own event loop.
  * :data:`dev_auth_router` — ``GET /dev-login`` mints an OWNER JWT for the seeded demo org and
    drops it in the ``maisha_jwt`` cookie the HTMX surface reads; ``GET /dev-logout`` clears it.

BOTH the minter (here, in the API process) and the JWKS publisher (the separate process) derive
the SAME Ed25519 key deterministically from ``MAISHA_SESSION_SECRET``, so they agree without any
shared state — and tokens survive a restart as long as the secret is stable.

HARD-GATED: :func:`app.main.create_app` mounts ``dev_auth_router`` only when
``MAISHA_DEV_AUTH=1`` AND ``MAISHA_ENVIRONMENT != "production"``. It is never wired in production;
production authentication remains Better Auth JWTs, verified and never minted.
"""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import get_settings
from app.core import betterauth

#: Demo credentials baked into the minted token — must match the demo tenant `app.dev.seed`
#: loads. The org id comes from MAISHA_SEED_ORG_ID (same env the seed reads), so the seeded
#: org-scoped rows (memory, audit chain) render for the signed-in user.
DEMO_SUB = "founder"
DEMO_EMAIL = "founder@acme-demo.in"
DEMO_ROLE = "owner"
TOKEN_TTL = timedelta(days=30)  # long, so a demo session never expires mid-poke


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _seed_bytes() -> bytes:
    """32-byte Ed25519 seed derived from the session secret — stable across processes/restarts."""
    secret = get_settings().session_secret
    return hashlib.sha256(f"maisha-dev-auth:{secret}".encode()).digest()


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes())


def key_id() -> str:
    """Deterministic ``kid`` — the token header and the published JWK must carry the same one."""
    return hashlib.sha256(_seed_bytes() + b"kid").hexdigest()[:16]


def public_jwk() -> dict[str, str]:
    raw = _private_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64u(raw),
        "kid": key_id(),
        "use": "sig",
        "alg": "EdDSA",
    }


def demo_org() -> str:
    return os.environ.get("MAISHA_SEED_ORG_ID", "demo-org")


def mint_demo_token(*, now: datetime | None = None) -> str:
    """Mint an OWNER JWT for the demo org, signed with the JWKS key, iss/aud = Better Auth URL.

    The claims are exactly what ``app.core.betterauth`` demands: ``sub``, ``email``,
    ``activeOrganizationId`` and a mappable ``role``, plus verified ``exp``/``iss``/``aud``.
    """
    issued = now or datetime.now(UTC)
    base = betterauth.better_auth_base_url()  # iss/aud default to this on both sides
    payload: dict[str, Any] = {
        "sub": DEMO_SUB,
        "email": DEMO_EMAIL,
        "iss": base,
        "aud": base,
        "iat": int(issued.timestamp()),
        "exp": int((issued + TOKEN_TTL).timestamp()),
        betterauth.ACTIVE_ORG_CLAIM: demo_org(),
        betterauth.ROLE_CLAIM: DEMO_ROLE,
    }
    return jwt.encode(payload, _private_key(), algorithm="EdDSA", headers={"kid": key_id()})


# ── JWKS publisher (runs as its own process) ─────────────────────────────────────────────────────

jwks_app = FastAPI(title="maisha-dev-auth (JWKS stand-in)")


@jwks_app.get("/api/auth/jwks")
async def _jwks() -> JSONResponse:
    return JSONResponse({"keys": [public_jwk()]})


@jwks_app.get("/health")
async def _jwks_health() -> dict[str, str]:
    return {"status": "ok"}


# ── one-click sign-in (mounted into the API process, public paths) ───────────────────────────────

dev_auth_router = APIRouter()


@dev_auth_router.get("/dev-login")
async def dev_login(request: Request, next: str = "/") -> RedirectResponse:
    """Demo sign-in: mint the OWNER token and plant it in the same cookie the HTMX surface reads.

    Same-origin (the API sets its own cookie), so it works without a separate auth host. Only
    reachable when the dev-auth gate is on (see ``app.main``)."""
    token = mint_demo_token()
    resp = RedirectResponse(url=next if next.startswith("/") else "/", status_code=303)
    resp.set_cookie(
        betterauth.TOKEN_COOKIE,
        token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return resp


@dev_auth_router.get("/dev-logout")
async def dev_logout() -> RedirectResponse:
    resp = RedirectResponse(url="/dev-login", status_code=303)
    resp.delete_cookie(betterauth.TOKEN_COOKIE, path="/")
    return resp
