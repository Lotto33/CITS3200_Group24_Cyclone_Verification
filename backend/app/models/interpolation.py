"""Interpolated best track: the 15-minute grid the verification is scored on.

Persists what
:mod:`app.services.interpolation.interpolate_best_track` writes to
``data/processed/best_track_interpolated.csv``.

``interpolation_run`` exists because the step size and the wind thresholds are
exactly what the science team will tune, and every contingency number
downstream depends on which values produced it. Without a run row you cannot
answer "which interpolation made these numbers", and re-running with a
different step would silently mix two grids in one table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.columns import JSONType, UtcDateTime
from app.models.enums import TrackDataset, sql_in_clause


class InterpolationRun(Base):
    __tablename__ = "interpolation_run"
    __table_args__ = (
        CheckConstraint(
            sql_in_clause("source_dataset", TrackDataset),
            name="source_dataset_valid",
        ),
        CheckConstraint("step_minutes > 0", name="step_minutes_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))

    source_dataset: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=TrackDataset.BOM_BEST_TRACK.value,
        doc="Which best_track_observation.dataset was the input. Only "
        "'bom_best_track' is viable: the OTCR reanalysis ends 2016-12-25 and "
        "contributes 58 rows inside the project period, so the loader refuses "
        "it rather than producing a near-empty grid.",
    )

    # Parameters, mirrored from interpolate_best_track / process_best_track so
    # a run is reproducible from its own row.
    step_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    project_start: Mapped[datetime | None] = mapped_column(
        UtcDateTime, doc="PROJECT_START: observations before this are excluded."
    )
    gf_threshold_kn: Mapped[float] = mapped_column(Float, nullable=False, default=34.0)
    sf_threshold_kn: Mapped[float] = mapped_column(Float, nullable=False, default=48.0)
    hf_threshold_kn: Mapped[float] = mapped_column(Float, nullable=False, default=64.0)
    mps_to_knots: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.94384
    )
    restricted_to_watch_warning: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Whether input was limited to disturbances with a GML watch or "
        "warning area.",
    )

    input_row_count: Mapped[int | None] = mapped_column(Integer)
    output_row_count: Mapped[int | None] = mapped_column(Integer)
    disturbance_count: Mapped[int | None] = mapped_column(Integer)
    code_version: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType, doc="Escape hatch for parameters added later."
    )

    points: Mapped[list["InterpolatedPoint"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InterpolationRun {self.id} step={self.step_minutes}min>"


class InterpolatedPoint(Base):
    __tablename__ = "interpolated_point"
    __table_args__ = (
        UniqueConstraint("run_id", "disturbance_pk", "tm"),
        Index(
            "ix_interpolated_point_run_id_disturbance_pk_tm",
            "run_id",
            "disturbance_pk",
            "tm",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("interpolation_run.id", ondelete="CASCADE"), nullable=False
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    tm: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    is_interpolated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        doc="False for a preserved original observation, True for a value the "
        "interpolator produced. Original observations are reproduced exactly, "
        "including explicit zeros and nulls.",
    )

    # Linearly interpolated fields (LINEAR_COLS in interpolate_best_track).
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    max_wind_spd: Mapped[float | None] = mapped_column(Float, doc="m/s.")
    position_uncertainty: Mapped[float | None] = mapped_column(
        Float, doc="km. Float here because interpolation yields fractional values."
    )

    # Wind radii, km. Float for the same reason. 0 still means "known absence"
    # and NULL "unknown" -- the interpolator deliberately leaves interior
    # values unknown when it cannot distinguish the two at the endpoints.
    mn_radius_gf_wind: Mapped[float | None] = mapped_column(Float)
    mn_radius_gf_secne: Mapped[float | None] = mapped_column(Float)
    mn_radius_gf_secse: Mapped[float | None] = mapped_column(Float)
    mn_radius_gf_secsw: Mapped[float | None] = mapped_column(Float)
    mn_radius_gf_secnw: Mapped[float | None] = mapped_column(Float)
    mn_radius_sf_wind: Mapped[float | None] = mapped_column(Float)
    mn_radius_sf_secne: Mapped[float | None] = mapped_column(Float)
    mn_radius_sf_secse: Mapped[float | None] = mapped_column(Float)
    mn_radius_sf_secsw: Mapped[float | None] = mapped_column(Float)
    mn_radius_sf_secnw: Mapped[float | None] = mapped_column(Float)
    mn_radius_hf_wind: Mapped[float | None] = mapped_column(Float)
    mn_radius_hf_secne: Mapped[float | None] = mapped_column(Float)
    mn_radius_hf_secse: Mapped[float | None] = mapped_column(Float)
    mn_radius_hf_secsw: Mapped[float | None] = mapped_column(Float)
    mn_radius_hf_secnw: Mapped[float | None] = mapped_column(Float)

    run: Mapped[InterpolationRun] = relationship(back_populates="points")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InterpolatedPoint run={self.run_id} {self.tm}>"
