"""SQLAlchemy declarative base. All ORM models inherit from ``Base`` so that
``Base.metadata.create_all`` builds the full schema (mirrors ``schema.sql``)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
