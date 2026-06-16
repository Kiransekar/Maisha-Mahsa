"""The EmailChannel: compose + dispatch domain emails through a transport."""

from __future__ import annotations

from typing import Any

from app.core.cfo import DailyBrief
from app.core.email.renderer import render, render_daily_brief
from app.core.email.transport import Transport


class EmailChannel:
    def __init__(self, transport: Transport, *, sender: str = "cfo@maisha-mahsa.local") -> None:
        self._transport = transport
        self._sender = sender

    async def _send(self, *, to: str, subject: str, html: str) -> str:
        await self._transport.send(to=to, subject=subject, html=html, sender=self._sender)
        return html

    async def send_daily_brief(
        self, *, to: str, brief: DailyBrief, company_name: str = "Maisha-Mahsa"
    ) -> str:
        html = render_daily_brief(brief, company_name=company_name)
        flagged = len(brief.needs_attention)
        subject = f"{company_name} — Daily CFO Brief ({brief.as_of})" + (
            f" · {flagged} need(s) attention" if flagged else " · all green"
        )
        return await self._send(to=to, subject=subject, html=html)

    async def send_compliance_alert(self, *, to: str, ctx: dict[str, Any]) -> str:
        html = render("compliance_alert.html", ctx=ctx)
        subject = f"Compliance Alert · {ctx['total']} filing(s) need attention"
        return await self._send(to=to, subject=subject, html=html)

    async def send_payroll_approval(self, *, to: str, ctx: dict[str, Any]) -> str:
        html = render("payroll_approval.html", ctx=ctx)
        subject = f"Payroll Approval · {ctx['month_year']} · {ctx['validation_status'].upper()}"
        return await self._send(to=to, subject=subject, html=html)

    async def send_investor_update(
        self, *, to: str, ctx: dict[str, Any], company_name: str = "Maisha-Mahsa"
    ) -> str:
        html = render("investor_update.html", ctx=ctx, company_name=company_name)
        subject = f"{company_name} — Investor Update · {ctx['period']}"
        return await self._send(to=to, subject=subject, html=html)
