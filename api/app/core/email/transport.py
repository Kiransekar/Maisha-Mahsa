"""Email transports. The transport is the network boundary — tests use ``InMemoryTransport``;
production uses ``SmtpTransport`` (aiosmtplib → MailHog locally, or a self-hosted SMTP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SentMessage:
    to: str
    subject: str
    html: str


@runtime_checkable
class Transport(Protocol):
    async def send(self, *, to: str, subject: str, html: str, sender: str) -> None: ...


@dataclass
class InMemoryTransport:
    """Captures sent messages instead of dispatching — for tests and dry runs."""

    sent: list[SentMessage] = field(default_factory=list)

    async def send(self, *, to: str, subject: str, html: str, sender: str) -> None:
        self.sent.append(SentMessage(to=to, subject=subject, html=html))


@dataclass
class SmtpTransport:
    """Sends via SMTP using aiosmtplib (imported lazily so the dependency is only needed
    when actually dispatching)."""

    host: str = "127.0.0.1"
    port: int = 1025  # MailHog default
    username: str | None = None
    password: str | None = None
    use_tls: bool = False

    async def send(self, *, to: str, subject: str, html: str, sender: str) -> None:
        from email.message import EmailMessage

        import aiosmtplib

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content("This message requires an HTML-capable client.")
        msg.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_tls=self.use_tls,
        )


def smtp_from_settings(settings: object) -> SmtpTransport:
    """Build an SmtpTransport from app settings (auth + TLS for a production relay)."""
    return SmtpTransport(
        host=settings.smtp_host,  # type: ignore[attr-defined]
        port=settings.smtp_port,  # type: ignore[attr-defined]
        username=settings.smtp_username or None,  # type: ignore[attr-defined]
        password=settings.smtp_password or None,  # type: ignore[attr-defined]
        use_tls=settings.smtp_use_tls,  # type: ignore[attr-defined]
    )
