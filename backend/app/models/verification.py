"""Verification products: the contingency tables and their summary.

These mirror ``data/contingency_tables/<distId>_table_{a,b,c,d}.csv`` plus
``_contingency_summary.csv``.

``Location`` and ``State`` in the CSVs resolve to ``town_id`` rather than being
repeated; the CSV export layer puts them back. Distances may be **negative** --
the sample data has values like -0.27 -- because a negative distance means the
town lies inside the area, so there is no non-negative check on them.

``contingency_matrix.csv`` gets no table: it is a rendering of the same four
counts plus totals, and storing it would be a second source of truth that can
drift. It is computed in the schema layer instead.
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
from app.models.enums import Outcome, SummaryScope, sql_in_clause


class VerificationRun(Base):
    """Provenance for one scoring pass, so a re-run cannot mix results."""

    __tablename__ = "verification_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))

    interpolation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("interpolation_run.id", ondelete="SET NULL"),
        doc="Which interpolated grid was scored. Null only for runs loaded "
        "from the pre-existing CSVs, whose grid predates the DB.",
    )
    forecast_source: Mapped[str | None] = mapped_column(
        String(24), default="gml_bulletins"
    )
    truth_dataset: Mapped[str | None] = mapped_column(String(24))
    town_count: Mapped[int | None] = mapped_column(Integer)
    disturbance_count: Mapped[int | None] = mapped_column(Integer)
    base_time_step_hours: Mapped[int | None] = mapped_column(Integer)
    code_version: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType, doc="Distance thresholds, watch/warning rules, season definition."
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VerificationRun {self.id} {self.label!r}>"


class ForecastAdviceDistance(Base):
    """Table A: forecast watch/warning distance per town per base time."""

    __tablename__ = "verification_forecast_distance"
    __table_args__ = (
        UniqueConstraint("run_id", "disturbance_pk", "base_time", "town_id"),
        Index(
            "ix_verification_forecast_distance_run_id_disturbance_pk",
            "run_id",
            "disturbance_pk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_run.id", ondelete="CASCADE"), nullable=False
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    base_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    town_id: Mapped[int] = mapped_column(
        ForeignKey("town.id", ondelete="CASCADE"), nullable=False
    )

    distance_to_watch_km: Mapped[float | None] = mapped_column(
        Float,
        doc="Signed km to the watch area; negative means inside it. NULL when "
        "the bulletin carried no watch area at all.",
    )
    distance_to_warning_km: Mapped[float | None] = mapped_column(
        Float, doc="Signed km to the warning area; NULL when there was none."
    )
    watch: Mapped[bool] = mapped_column(Boolean, nullable=False)
    warning: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ObservedWindDistance(Base):
    """Table B: observed wind-extent distances per town per time.

    The largest of these tables by a wide margin -- 70,630 rows for a single
    disturbance in the sample output.
    """

    __tablename__ = "verification_observed_distance"
    __table_args__ = (
        UniqueConstraint("run_id", "disturbance_pk", "town_id", "tm"),
        Index(
            "ix_verification_observed_distance_run_id_disturbance_pk",
            "run_id",
            "disturbance_pk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_run.id", ondelete="CASCADE"), nullable=False
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    town_id: Mapped[int] = mapped_column(
        ForeignKey("town.id", ondelete="CASCADE"), nullable=False
    )
    tm: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        doc="Interpolated-grid time. The CSV column is 'Time', not 'Base time'.",
    )

    analysis_uncertainty_km: Mapped[float | None] = mapped_column(Float)
    distance_to_gale_km: Mapped[float | None] = mapped_column(Float)
    distance_to_storm_km: Mapped[float | None] = mapped_column(Float)
    distance_to_hurricane_km: Mapped[float | None] = mapped_column(Float)


class ObservedTownImpact(Base):
    """Table C: whether each town was observed affected, per base time."""

    __tablename__ = "verification_observed_event"
    __table_args__ = (
        UniqueConstraint("run_id", "disturbance_pk", "base_time", "town_id"),
        Index(
            "ix_verification_observed_event_run_id_disturbance_pk",
            "run_id",
            "disturbance_pk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_run.id", ondelete="CASCADE"), nullable=False
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    base_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    town_id: Mapped[int] = mapped_column(
        ForeignKey("town.id", ondelete="CASCADE"), nullable=False
    )
    observed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class VerificationPair(Base):
    """Table D: the forecast/observed pair that the contingency table counts.

    ``outcome`` is stored rather than derived on read, so the summary is a
    single indexed GROUP BY instead of a CASE expression -- which matters once
    the API serves per-season and per-state breakdowns. The loader asserts it
    agrees with ``forecast``/``observed``.
    """

    __tablename__ = "verification_pair"
    __table_args__ = (
        UniqueConstraint("run_id", "disturbance_pk", "base_time", "town_id"),
        CheckConstraint(sql_in_clause("outcome", Outcome), name="outcome_valid"),
        Index("ix_verification_pair_run_id_outcome", "run_id", "outcome"),
        Index("ix_verification_pair_run_id_season", "run_id", "season"),
        Index(
            "ix_verification_pair_run_id_disturbance_pk", "run_id", "disturbance_pk"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_run.id", ondelete="CASCADE"), nullable=False
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    base_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    town_id: Mapped[int] = mapped_column(
        ForeignKey("town.id", ondelete="CASCADE"), nullable=False
    )
    season: Mapped[str | None] = mapped_column(String(7))
    forecast: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)


class VerificationSummary(Base):
    """Cached contingency counts for one run, optionally per season/state."""

    __tablename__ = "verification_summary"
    __table_args__ = (
        UniqueConstraint("run_id", "scope", "scope_key"),
        CheckConstraint(sql_in_clause("scope", SummaryScope), name="scope_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("verification_run.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SummaryScope.ALL.value
    )
    scope_key: Mapped[str | None] = mapped_column(
        String(40), doc="The disturbance id / season / state, or NULL for scope 'all'."
    )

    hit: Mapped[int] = mapped_column(Integer, nullable=False)
    false_alarm: Mapped[int] = mapped_column(Integer, nullable=False)
    miss: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_negative: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped[VerificationRun] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VerificationSummary run={self.run_id} {self.scope}"
            f"{'/' + self.scope_key if self.scope_key else ''} n={self.total}>"
        )
