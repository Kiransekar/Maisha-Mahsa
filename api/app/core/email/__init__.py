"""The email channel (PRD §6): render domain-health briefs / approval / compliance emails
and dispatch them via a pluggable transport (in-memory for tests, SMTP for prod)."""

from app.core.email.channel import EmailChannel
from app.core.email.transport import InMemoryTransport, SmtpTransport, Transport

__all__ = ["EmailChannel", "InMemoryTransport", "SmtpTransport", "Transport"]
