"""Jinja2 rendering for emails. Templates live in ``app/web/templates/email/``."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.cfo import DailyBrief, brief_payload
from app.core.money import Paise

_EMAIL_DIR = Path(__file__).resolve().parents[2] / "web" / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(_EMAIL_DIR)),
    autoescape=select_autoescape(["html"]),
)
# `{{ amount_paise|rupees }}` -> Indian-grouped ₹ string.
_env.filters["rupees"] = lambda paise: Paise(int(paise)).format_inr()


def render_daily_brief(brief: DailyBrief, *, company_name: str = "Maisha-Mahsa") -> str:
    template = _env.get_template("daily_brief.html")
    return template.render(brief=brief_payload(brief), company_name=company_name)


def render(template_name: str, **context: object) -> str:
    """Render any email template with the shared environment (incl. the `rupees` filter)."""
    return _env.get_template(template_name).render(**context)
