"""Shared FastAPI dependencies."""

from __future__ import annotations

from app.config import get_settings
from app.core.mahsa_client import MahsaClient


def get_mahsa() -> MahsaClient:
    return MahsaClient(get_settings().mahsa_url)
