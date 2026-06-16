"""Runtime settings. Env-driven (12-factor), with safe local defaults."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAISHA_", env_file=".env", extra="ignore")

    app_name: str = "Maisha-Mahsa"
    version: str = "4.0.0"

    # Mahsa sidecar
    mahsa_url: str = "http://127.0.0.1:8088"

    # Database — single SQLite file (PRD §3). ":memory:" handled by tests.
    database_url: str = "sqlite:///./data/maisha.db"

    # Single-user auth (PRD §11.1). Set MAISHA_APP_PASSWORD in production.
    app_password: str = "change-me"

    # Default acting user for audit entries until full auth lands.
    default_user_id: str = "founder"

    # Email channel (PRD §6). SMTP defaults target a local MailHog.
    cfo_email: str = "founder@maisha-mahsa.local"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    email_sender: str = "cfo@maisha-mahsa.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
