"""Better Auth JWT verification (WS4.3-betterauth-api · P2-6 hmac-retire).

Better Auth (better-auth.com) is TypeScript-only and runs in the Node layer; it owns
credentials, 2FA and sessions. This module does exactly one job: verify the JWTs it issues and
resolve them to a :class:`app.core.principal.Principal`. It never runs, reimplements, or
proxies Better Auth itself. The legacy HMAC-cookie password flow (``app.core.auth``) is DELETED
(P2-6): the SPA carries the JWT in the Authorization header, the HTMX surface carries the SAME
JWT in the :data:`TOKEN_COOKIE` cookie, and both go through the same JWKS verification below —
one auth system, one verifier.

Verified facts this module is built against (better-auth.com, fetched this session):
  - JWKS endpoint: ``BASE_URL + "/api/auth/jwks"``.
  - Default signing algorithm EdDSA (Ed25519); ES256/RS256 (among others) also supported.
  - Issuer and audience both default to BASE_URL.
  - The organization plugin puts ``activeOrganizationId`` on the session/token and models
    members with roles (owner/admin/member by default, plus dynamic custom roles).

§0.8 SECURITY:
  - Algorithms are PINNED to an explicit allow-list (never "none", never taken from the token).
  - Signature, ``exp``, ``iss`` and ``aud`` are all required and verified — PyJWT verifies all
    four whenever they are supplied to ``jwt.decode`` with ``options`` requiring them; nothing
    in this module ever passes ``verify_signature=False``.
  - ``org_id`` comes from the token's ``activeOrganizationId`` claim ONLY — never a request
    body, query param, or client-controlled header.
  - FAIL CLOSED throughout: an unreachable JWKS endpoint, an unknown ``kid``, a bad signature,
    an expired/wrong-issuer/wrong-audience token, a missing org, or an unmapped role all deny
    the request. There is no fallback to accepting an unverified token and no fallback to the
    legacy shared-password auth.
"""

from __future__ import annotations

import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.core.principal import Principal, map_better_auth_role, mfa_required

#: Explicit allow-list. PyJWT's "none" algorithm is never in this list and never will be.
ALLOWED_ALGORITHMS: tuple[str, ...] = ("EdDSA", "ES256", "RS256")

#: Better Auth organization-plugin claim carrying the caller's active org (verified fact above).
ACTIVE_ORG_CLAIM = "activeOrganizationId"
ROLE_CLAIM = "role"

#: The HTMX surface's JWT carrier (P2-6). The frontend/Better Auth TS layer sets this cookie to
#: the SAME JWT the SPA sends as a bearer header; verification is identical either way.
TOKEN_COOKIE = "maisha_jwt"


def _env(name: str) -> str:
    return os.environ.get(name, "")


def better_auth_base_url() -> str:
    """``MAISHA_BETTER_AUTH_URL`` — the owner's Better Auth server base URL. Env only."""
    return _env("MAISHA_BETTER_AUTH_URL")


def better_auth_jwks_url() -> str:
    base = better_auth_base_url()
    return base.rstrip("/") + "/api/auth/jwks"


def better_auth_issuer() -> str:
    """``MAISHA_BETTER_AUTH_ISSUER``, defaulting to the base URL (Better Auth's own default)."""
    return _env("MAISHA_BETTER_AUTH_ISSUER") or better_auth_base_url()


def better_auth_audience() -> str:
    """``MAISHA_BETTER_AUTH_AUDIENCE``, defaulting to the base URL (Better Auth's own default)."""
    return _env("MAISHA_BETTER_AUTH_AUDIENCE") or better_auth_base_url()


def better_auth_mfa_claim() -> str:
    """``MAISHA_BETTER_AUTH_MFA_CLAIM`` — name of the boolean JWT claim asserting the caller
    completed 2FA. UNSET = MFA is not enforced by this API (see :func:`assert_mfa_satisfied`)."""
    return _env("MAISHA_BETTER_AUTH_MFA_CLAIM").strip()


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """One cached client per JWKS URL. ``PyJWKClient`` already implements the caching this
    ticket asks for: a JWK-set cache (keys "change rarely") plus an LRU signing-key cache, and
    ``get_signing_key`` refreshes ONCE on a ``kid`` miss before giving up — exactly the
    fail-once-then-fail-closed behaviour required, with no re-implementation needed here."""
    return PyJWKClient(jwks_url, cache_keys=True, cache_jwk_set=True, lifespan=300)


class AuthError(Exception):
    """Token is missing, malformed, unverifiable, expired, or wrong iss/aud. -> HTTP 401."""


class NoOrgError(Exception):
    """Token verified, but carries no ``activeOrganizationId`` or an unmapped role. -> HTTP 403."""


def decode_claims(token: str, *, jwks_url: str, issuer: str, audience: str) -> dict[str, object]:
    """Verify signature + exp + iss + aud and return the raw claims. Fail-closed.

    Raises :class:`AuthError` for EVERY failure mode: JWKS unreachable, unknown ``kid``, bad
    signature, expired token, wrong issuer, wrong audience, or missing ``sub``/``email`` (a
    Principal cannot be built without them). Never returns unverified claims.
    """
    if not jwks_url or not issuer or not audience:
        # Owner hasn't configured Better Auth yet — fail closed, not "trust anything".
        raise AuthError("better auth not configured (missing url/issuer/audience)")
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    except (PyJWKClientError, jwt.exceptions.InvalidTokenError) as exc:
        # PyJWKClientError covers: JWKS endpoint unreachable, no signing keys, unknown kid even
        # after the client's built-in one-shot refresh.
        # InvalidTokenError covers a MALFORMED token: get_signing_key_from_jwt has to parse the
        # header to read the kid, so garbage input ("not-a-jwt") raises DecodeError HERE, before
        # the decode below. Caught by tests/integration/test_auth_e2e.py::
        # test_malformed_token_is_401 — uncaught it surfaced as a 500, not a 401.
        # Fail closed either way — never falls back to an unverified decode.
        raise AuthError(f"jwks lookup failed: {exc}") from exc

    try:
        claims: dict[str, object] = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(ALLOWED_ALGORITHMS),
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.exceptions.InvalidTokenError as exc:
        # ExpiredSignatureError, InvalidSignatureError, InvalidIssuerError,
        # InvalidAudienceError, MissingRequiredClaimError, DecodeError, ... all land here.
        raise AuthError(f"token rejected: {exc}") from exc

    if not claims.get("email"):
        raise AuthError("token missing required 'email' claim")
    return claims


def principal_from_claims(claims: dict[str, object]) -> Principal:
    """Build a :class:`Principal` from already-verified claims. Fail-closed on org/role.

    ``org_id`` comes from ``activeOrganizationId`` ONLY — an absent claim does NOT default to
    any org (no first/any-org fallback). An unrecognised Better Auth role is denied, never
    silently downgraded. Both failure modes raise :class:`NoOrgError` (HTTP 403 — a valid,
    correctly-signed token that simply isn't authorized for anything yet).
    """
    org_id = claims.get(ACTIVE_ORG_CLAIM)
    if not org_id or not isinstance(org_id, str):
        raise NoOrgError("token has no active organization")
    raw_role = claims.get(ROLE_CLAIM)
    role = map_better_auth_role(raw_role if isinstance(raw_role, str) else None)
    if role is None:
        raise NoOrgError(f"unmapped or unknown role: {raw_role!r}")
    return Principal(
        user_id=str(claims["sub"]), org_id=org_id, role=role, email=str(claims["email"])
    )


def assert_mfa_satisfied(claims: dict[str, object], principal: Principal) -> None:
    """Enforce the ported §WS4.3 MFA policy (:func:`app.core.principal.mfa_required`).

    OPT-IN, and deliberately so: Better Auth's two-factor plugin owns the 2FA mechanism, but
    whether its ``twoFactorEnabled`` flag reaches the JWT depends on the owner's server-side
    payload configuration, which this repo cannot see. Rather than invent a claim name and ship
    a check that silently passes on every token (the exact hollow-control failure this round
    exists to stop), enforcement is off until the owner names the claim in
    ``MAISHA_BETTER_AUTH_MFA_CLAIM``. Once named, a privileged caller whose token does not carry
    it truthy is DENIED (403) — never waved through.
    """
    claim_name = better_auth_mfa_claim()
    if not claim_name or not mfa_required(principal.role):
        return
    if not claims.get(claim_name):
        raise NoOrgError(f"role {principal.role.value} requires 2FA; token lacks {claim_name!r}")


def verify_token(token: str, *, jwks_url: str, issuer: str, audience: str) -> Principal:
    """Full verify-and-resolve pipeline. Raises :class:`AuthError`/:class:`NoOrgError`."""
    claims = decode_claims(token, jwks_url=jwks_url, issuer=issuer, audience=audience)
    principal = principal_from_claims(claims)
    assert_mfa_satisfied(claims, principal)
    return principal


def bearer_token(request: Request) -> str | None:
    """The raw token from an ``Authorization: Bearer <token>`` header, else ``None``."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def request_token(request: Request) -> str | None:
    """The request's JWT: bearer header first (SPA/API), else the :data:`TOKEN_COOKIE` cookie
    (HTMX pages). A present bearer header always wins — a bad header token is a rejected
    request, never a fall-through to the cookie (the P2-6 no-fallback rule)."""
    return bearer_token(request) or request.cookies.get(TOKEN_COOKIE) or None


def principal_from_request(request: Request) -> Principal:
    """Verify this request's token (header or cookie) against the configured Better Auth JWKS.

    THE one entry point production authentication goes through (see the ``_authenticate``
    middleware in :mod:`app.main`). Raises :class:`AuthError` (-> 401) for a missing, malformed,
    expired, wrongly-signed, wrong-issuer/audience or unverifiable token — including an
    unreachable JWKS endpoint — and :class:`NoOrgError` (-> 403) for a verified token with no
    active org, an unmapped role, or unsatisfied MFA. It never returns an unverified Principal.
    """
    token = request_token(request)
    if token is None:
        raise AuthError("missing bearer token")
    return verify_token(
        token,
        jwks_url=better_auth_jwks_url(),
        issuer=better_auth_issuer(),
        audience=better_auth_audience(),
    )


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: ``Depends(get_principal)`` — the verified caller.

    Returns the Principal the ``_authenticate`` middleware already verified and stashed on
    ``request.state`` (one signature check per request, not one per dependency). Fail-closed: if
    the middleware did not authenticate this request — legacy cookie session, or the middleware
    somehow bypassed — there is no Principal and this raises 401. It never re-derives identity
    from anything client-controlled.
    """
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="no verified principal on request")
    return principal


if __name__ == "__main__":  # ponytail: one runnable check for the config-plumbing path
    os.environ.pop("MAISHA_BETTER_AUTH_URL", None)
    os.environ.pop("MAISHA_BETTER_AUTH_ISSUER", None)
    os.environ.pop("MAISHA_BETTER_AUTH_AUDIENCE", None)
    assert better_auth_base_url() == ""
    assert better_auth_jwks_url() == "/api/auth/jwks"
    os.environ["MAISHA_BETTER_AUTH_URL"] = "https://auth.example.com"
    assert better_auth_jwks_url() == "https://auth.example.com/api/auth/jwks"
    assert better_auth_issuer() == "https://auth.example.com"
    assert better_auth_audience() == "https://auth.example.com"
    os.environ["MAISHA_BETTER_AUTH_ISSUER"] = "https://issuer.example.com"
    assert better_auth_issuer() == "https://issuer.example.com"
    del os.environ["MAISHA_BETTER_AUTH_URL"]
    del os.environ["MAISHA_BETTER_AUTH_ISSUER"]
    try:
        decode_claims("x.y.z", jwks_url="", issuer="", audience="")
    except AuthError:
        pass
    else:
        raise AssertionError("unconfigured better auth must fail closed")

    # P2-6: header wins over cookie; cookie alone works; neither -> None.
    from types import SimpleNamespace as _NS

    def _req(hdr: str, ck: dict[str, str]) -> Request:
        return _NS(headers={"authorization": hdr}, cookies=ck)  # type: ignore[return-value]

    assert request_token(_req("Bearer h.h.h", {TOKEN_COOKIE: "c.c.c"})) == "h.h.h"
    assert request_token(_req("", {TOKEN_COOKIE: "c.c.c"})) == "c.c.c"
    assert request_token(_req("", {})) is None
    print("betterauth self-check ok")
