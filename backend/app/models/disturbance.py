"""One row per tropical cyclone / tropical low.

``data/best_track.csv`` holds 1,133 distinct ``DISTURBANCE_ID`` values; only
136 have GML bulletins, and of those 30 have **no** best track at all -- mostly
test ids (``_97U``/``_98U``/``_99U``) plus real systems such as
``AU201819_01U`` from seasons BoM has not finished reanalysing. So a bulletin
never implies observations exist, and ``has_best_track`` is genuinely false for
some systems that do have bulletins.
"""

from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.columns import UtcDateTime


class Disturbance(TimestampMixin, Base):
    __tablename__ = "disturbance"
    __table_args__ = (
        Index("ix_disturbance_region", "region"),
        Index("ix_disturbance_season", "season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disturbance_id: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        unique=True,
        doc="BoM DISTURBANCE_ID, e.g. 'AU201617_19U'. The natural key.",
    )
    name: Mapped[str | None] = mapped_column(
        String(30),
        doc="BoM NAME, stripped. Constant per disturbance in the CSV, so it "
        "lives here rather than being repeated on 31,706 observation rows. "
        "'unnamed' means no naming convention existed at the time.",
    )
    region: Mapped[str | None] = mapped_column(
        String(8),
        doc="NT/QLD/WA, from the GML directory. Null for systems that appear "
        "only in the best-track CSV.",
    )
    season: Mapped[str | None] = mapped_column(
        String(7),
        doc="Derived, e.g. '2016-17'. See app.services.loaders.common.season_of.",
    )
    type_code: Mapped[str | None] = mapped_column(
        String(1),
        doc="BoM TYPE. Observed in the data: T, L, E, D, O.",
    )

    is_test: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True for BoM test products: ids ending 97U/98U/99U, or a "
        "distName like 'TEST-WA-2016'.",
    )
    has_watch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_best_track: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bulletin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_issue: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_issue: Mapped[datetime | None] = mapped_column(UtcDateTime)
    first_obs_tm: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_obs_tm: Mapped[datetime | None] = mapped_column(UtcDateTime)

    observations: Mapped[list["BestTrackObservation"]] = relationship(  # noqa: F821
        back_populates="disturbance",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    bulletins: Mapped[list["Bulletin"]] = relationship(  # noqa: F821
        back_populates="disturbance",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Disturbance {self.disturbance_id} {self.name!r}>"
