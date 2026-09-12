"""BoM code lookup tables.

One generic ``code_domain`` / ``code_value`` pair rather than ~13 near-identical
enum tables. Every domain in TC_Database_Structure_Oct2011.pdf has the same
shape (code -> description, NULL = unknown), several are *shared* by more than
one column -- ``radius_method`` by the four ``MN_RADIUS_*_METHOD`` columns,
``wind_method`` by ``MAX_WIND_SPD_METHOD`` and ``MAX_REP_WIND_METHOD``,
``wave_swell_method`` by ``MAX_REP_WAV_METHOD`` and ``MAX_REP_SWL_METHOD`` --
and the only query anyone runs is "give me the label for this code".

Note there is deliberately **no** foreign key from the observation columns to
``code_value``: the data runs to 2025 while the spec is from 2011, and
``PRES_WIND_RELATION_USED`` already carries code ``40`` on 71 real rows that
the PDF does not list. A hard FK would abort a 31,706-row ingest.
"""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CodeDomain(Base):
    __tablename__ = "code_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        unique=True,
        doc="Domain key, e.g. 'cyc_type'.",
    )
    label: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    values: Mapped[list["CodeValue"]] = relationship(
        back_populates="domain",
        cascade="all, delete-orphan",
        order_by="CodeValue.sort_order",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CodeDomain {self.code}>"


class CodeValue(Base):
    __tablename__ = "code_value"
    __table_args__ = (
        UniqueConstraint("domain_id", "code"),
        Index("ix_code_value_domain_id", "domain_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("code_domain.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        doc="Raw code as it appears in the CSV. String, not int, so the "
        "char-valued 'type' domain (D/T/E/L/O/U) shares this table.",
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    domain: Mapped[CodeDomain] = relationship(back_populates="values")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CodeValue {self.code}={self.description!r}>"
