"""Declarative base and shared model mixins.

The explicit ``naming_convention`` is load-bearing, not cosmetic: SQLite cannot
``ALTER`` a constraint, so Alembic has to recreate whole tables in "batch"
mode, and it can only recreate constraints that have names. Without this,
every migration after the first becomes hand-written SQL.
"""

from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.columns import UtcDateTime

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Adds a server-defaulted ``created_at``."""

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
        doc="Row insertion time (UTC).",
    )
