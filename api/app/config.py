"""Runtime settings. Env-driven (12-factor), with safe local defaults."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Shipped default for the preview-token HMAC key — production refuses to boot with it.
DEFAULT_SESSION_SECRET = "dev-insecure-session-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAISHA_", env_file=".env", extra="ignore")

    app_name: str = "Maisha-Mahsa"
    version: str = "4.0.0"

    # Mahsa sidecar
    mahsa_url: str = "http://127.0.0.1:8088"

    # Database — single SQLite file (PRD §3). ":memory:" handled by tests.
    database_url: str = "sqlite:///./data/maisha.db"

    # HMAC key for action preview tokens (app/web/api_actions.py). The old password-login
    # cookie signing is retired (P2-6) — auth is Better Auth JWT only (app/core/betterauth.py).
    session_secret: str = DEFAULT_SESSION_SECRET
    environment: str = "development"  # "production" refuses default/missing secrets at boot
    # Where an unauthenticated browser is sent to sign in: the SPA's Better Auth sign-in route.
    # Override (MAISHA_SIGNIN_URL) when the frontend is served from a different origin.
    signin_url: str = "/sign-in"

    # WS10.2 — CERT-In posture: severity events (unhandled 5xx, and anything else that calls
    # app.core.alerting.emit) POST a JSON alert here (e.g. a Slack/Discord/ops webhook or an
    # internal alertmanager receiver). Empty = alerts log locally only (dev default).
    # OWNER-STEP: point this at a real webhook before GA — see docs/DEPLOYMENT.md §10.
    alert_webhook_url: str = ""

    # Filer GSTIN for GSTR-1 JSON export (set MAISHA_COMPANY_GSTIN in production).
    company_gstin: str = ""
    # GST filing profile for the QRMP/composition obligation calendar (WS1.D2):
    # "monthly" | "qrmp" | "composition". Set MAISHA_GST_FILING_PROFILE per registration.
    gst_filing_profile: str = "monthly"

    # Default acting user for audit entries until full auth lands.
    default_user_id: str = "founder"

    # Email channel (PRD §6). SMTP defaults target a local MailHog.
    cfo_email: str = "founder@maisha-mahsa.local"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str = ""  # set for an authenticated production relay
    smtp_password: str = ""
    smtp_use_tls: bool = False  # True for a TLS SMTP relay (e.g. port 465)
    email_sender: str = "cfo@maisha-mahsa.local"

    # LLM / Maisha drafting layer (PRD §10 Layer 1, CLAUDE.md §7). The model only *drafts* —
    # every number it states is recomputed by Mahsa downstream. Ollama (local) is the default;
    # Claude is an explicit fallback. "off" disables the LLM step (run_loop stays deterministic).
    llm_provider: str = "off"  # "ollama" | "claude" | "off"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    claude_model: str = "claude-opus-4-8"
    claude_api_key: str = ""
    claude_base_url: str = "https://api.anthropic.com"
    llm_temperature: float = 0.0  # determinism (paired with the pass^k eval gate)
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2  # bounded regenerate-on-unbacked-number before template fallback

    # Scheduler (PRD Layer 6): the daily CFO brief + snapshot capture run at this local time.
    brief_hour: int = 20  # 8pm
    brief_minute: int = 0
    brief_tz: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
