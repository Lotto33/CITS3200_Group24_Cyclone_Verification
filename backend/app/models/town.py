"""Tropical-cyclone locations (the "Towns" layer).

Source: the ``TC Locations`` sheet of ``data/towns.xlsx``.

The sheet has **472 rows but only 466 distinct locations**. Six QLD entries --
Bamaga, Carmila, Hayman Is, QLD/NSW Border, Sandy Cape and Thursday Is --
appear twice at *identical* coordinates, once in ``qld_towns`` and once in
``qld_coastal_threat_area_locations``. They are one place in two groups, not
two places, so town group is a many-to-many and ``coastal_order`` belongs on
the membership: Bamaga is 81 in ``qld_towns`` and null in the threat-area
group.

Deduplicating also makes ``(name, state)`` a usable key for the contingency
tables, which identify a location by name alone in tables B and C.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Town(TimestampMixin, Base):
    __tablename__ = "town"
    __table_args__ = (
        UniqueConstraint("name", "state"),
        CheckConstraint(
            "lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180",
            name="coords_in_range",
        ),
        Index("ix_town_state", "state"),
        Index("ix_town_lat_lon", "lat", "lon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    is_major: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_island: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    groups: Mapped[list["TownGroupMembership"]] = relationship(
        back_populates="town",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Town {self.name} ({self.state})>"


class TownGroupMembership(Base):
    __tablename__ = "town_group_membership"
    __table_args__ = (
        UniqueConstraint("town_id", "town_group"),
        Index("ix_town_group_membership_town_group", "town_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    town_id: Mapped[int] = mapped_column(
        ForeignKey("town.id", ondelete="CASCADE"), nullable=False
    )
    town_group: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        doc="Sheet 'Town Group', e.g. 'qld_towns'.",
    )
    coastal_order: Mapped[float | None] = mapped_column(
        Float,
        doc="Sort key along the coast within this group. Float, not int: the "
        "sheet uses fractional values (19.1, 20.1, 20.2, 25.5, ...) to insert "
        "locations between existing entries, so truncating to int would "
        "collapse 20.1 and 20.2 onto 20 and destroy the ordering this column "
        "exists to express. Null for inland locations and for groups that do "
        "not order their members -- must stay nullable rather than default 0.",
    )

    town: Mapped[Town] = relationship(back_populates="groups")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TownGroupMembership {self.town_group} #{self.coastal_order}>"
