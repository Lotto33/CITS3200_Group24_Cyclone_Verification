"""Ingest audit trail.

This is the table that makes the guarantees in the loaders *testable over
time* rather than something that scrolls past on stdout: the blank-vs-zero
counts per column, code values absent from the 2011 spec, and town rows whose
duplicate entries disagree all land in ``stats``.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.columns import JSONType, UtcDateTime
from app.models.enums import IngestKind, IngestStatus, sql_in_clause


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = (
        CheckConstraint(sql_in_clause("kind", IngestKind), name="kind_valid"),
        CheckConstraint(sql_in_clause("status", IngestStatus), name="status_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str | None] = mapped_column(Text, doc="Input path or glob.")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=IngestStatus.RUNNING.value
    )
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str | None] = mapped_column(
        String(40), doc="Short git revision of the code that ran."
    )
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IngestRun {self.id} {self.kind} {self.status}>"
