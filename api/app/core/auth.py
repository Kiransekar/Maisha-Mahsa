"""Single-user authentication and secret hardening (LAUNCH_READINESS P1-AUTH / P1-SECRETS).

One operator, one password (``MAISHA_APP_PASSWORD``), authenticated by a stdlib-HMAC-signed
cookie — no session store, no extra dependency. The login guard protects every route except
the public allowlist. ponytail: single-user, constant-time checks; swap in scrypt hashes +
a users table only if this ever becomes multi-user.
"""

from __future__ import annotations

import hmac
from hashlib import sha256

COOKIE_NAME = "maisha_auth"
DEFAULT_PASSWORD = "change-me"
DEFAULT_SESSION_SECRET = "dev-insecure-session-secret-change-me"


def verify_password(supplied: str, expected: str) -> bool:
    """Constant-time password check (no timing oracle)."""
    return hmac.compare_digest(supplied.encode(), expected.encode())


def sign(secret: str) -> str:
    """The opaque session token: HMAC(secret, 'authed'). Rotating the secret logs everyone out."""
    return hmac.new(secret.encode(), b"authed", sha256).hexdigest()


def valid_cookie(value: str | None, secret: str) -> bool:
    return value is not None and hmac.compare_digest(value, sign(secret))


def is_public(path: str) -> bool:
    """Routes reachable without logging in."""
    return path == "/health" or path.startswith("/login") or path.startswith("/static")


def assert_production_secrets(
    *, environment: str, app_password: str, session_secret: str
) -> None:
    """Refuse to boot in production with the shipped default secrets (P1-SECRETS)."""
    if environment != "production":
        return
    bad = []
    if app_password == DEFAULT_PASSWORD:
        bad.append("MAISHA_APP_PASSWORD")
    if session_secret == DEFAULT_SESSION_SECRET:
        bad.append("MAISHA_SESSION_SECRET")
    if bad:
        raise RuntimeError(
            "Refusing to start in production with default secrets: "
            + ", ".join(bad)
            + ". Set them in the environment (see .env.example)."
        )


if __name__ == "__main__":  # ponytail: one runnable check for the security path
    assert verify_password("hunter2", "hunter2")
    assert not verify_password("hunter2", "hunter3")
    s = "secret"
    assert valid_cookie(sign(s), s)
    assert not valid_cookie(sign("other"), s)
    assert not valid_cookie(None, s)
    assert is_public("/health") and is_public("/static/app.css") and is_public("/login")
    assert not is_public("/") and not is_public("/d/gst")
    assert_production_secrets(
        environment="development",
        app_password=DEFAULT_PASSWORD,
        session_secret=DEFAULT_SESSION_SECRET,
    )
    try:
        assert_production_secrets(
            environment="production", app_password=DEFAULT_PASSWORD, session_secret="x"
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("production must refuse default password")
    print("auth self-check ok")
