"""Run the main data processing pipeline in order."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.best_track import BestTrackObservation
from app.models.disturbance import Disturbance
from app.models.interpolation import InterpolatedPoint, InterpolationRun
from app.models.enums import IngestKind
from app.services.loaders.best_track import (
    load_best_track,
    read_best_track_csv,
)
from app.services.loaders.codes_seed import seed_code_tables
from app.services.loaders.common import Stats, ingest_run
from app.services.loaders.gml import (
    DEFAULT_BATCH_FILES,
    load_bulletins,
)
from app.services.loaders.interpolation import load_interpolation
from app.services.loaders.towns import (
    load_towns,
    read_towns_sheet,
)


def _load_codes() -> dict[str, int]:
    """Load BoM code lookup tables."""
    with SessionLocal() as session:
        with ingest_run(
            session,
            IngestKind.CODES,
            source="TC_Database_Structure_Oct2011.pdf",
        ) as run:
            domain_count, value_count = seed_code_tables(session)

            run.rows_read = value_count
            run.rows_written = value_count

        session.commit()

    return {
        "domains": domain_count,
        "values": value_count,
    }


def _load_town_data(
    towns_path: Path | None = None,
) -> dict[str, int]:
    """Load town/location data."""
    with SessionLocal() as session:
        stats = Stats()
        frame = read_towns_sheet(towns_path)

        with ingest_run(
            session,
            IngestKind.TOWNS,
            source=str(towns_path or "towns.xlsx"),
        ) as run:
            counts = load_towns(
                session,
                frame,
                stats=stats,
            )

            run.rows_read = counts["rows_read"]
            run.rows_written = counts["towns"]
            run.rows_skipped = counts["skipped"]
            run.stats = stats.as_dict()

        session.commit()

    return counts


def _load_best_track_data(
    best_track_path: Path | None = None,
) -> dict[str, int]:
    """Load BoM best-track data."""
    with SessionLocal() as session:
        stats = Stats()
        frame = read_best_track_csv(best_track_path)

        with ingest_run(
            session,
            IngestKind.BEST_TRACK,
            source=str(best_track_path or "best_track.csv"),
        ) as run:
            counts = load_best_track(
                session,
                frame,
                ingest_run_id=run.id,
                stats=stats,
            )

            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()

        session.commit()

    return counts


def _load_gml_data(
    *,
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_FILES,
) -> dict[str, int]:
    """Load all GML bulletins."""
    with SessionLocal() as session:
        stats = Stats()

        with ingest_run(
            session,
            IngestKind.GML,
            source="all regions",
        ) as run:
            counts = load_bulletins(
                session,
                region=None,
                limit=None,
                force=force,
                ingest_run_id=run.id,
                stats=stats,
                batch_size=batch_size,
            )

            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.rows_skipped = counts["rows_skipped"]
            run.stats = stats.as_dict()

        session.commit()

    return counts


def _run_interpolation(
    *,
    step_minutes: int = 15,
    label: str = "data pipeline",
) -> dict[str, int]:
    """Interpolate relevant best-track systems."""
    with SessionLocal() as session:
        stats = Stats()

        with ingest_run(
            session,
            IngestKind.INTERPOLATION,
            source="best_track_observation",
        ) as run:
            counts = load_interpolation(
                session,
                step_minutes=step_minutes,
                watch_warning_only=True,
                label=label,
                replace=True,
                stats=stats,
            )

            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()

        session.commit()

    return counts

def _validate_pipeline(
    interpolation_run_id: int,
) -> dict[str, int | list[str]]:
    """Check the interpolation output."""
    with SessionLocal() as session:
        run = session.get(InterpolationRun, interpolation_run_id)

        if run is None:
            raise RuntimeError(
                f"Interpolation run {interpolation_run_id} was not found"
            )

        relevant_condition = (
            Disturbance.has_watch | Disturbance.has_warning
        )

        relevant_count = session.execute(
            select(func.count())
            .select_from(Disturbance)
            .where(relevant_condition)
        ).scalar_one()

        input_conditions = [
            BestTrackObservation.dataset == run.source_dataset,
        ]

        if run.project_start is not None:
            input_conditions.append(
                BestTrackObservation.tm >= run.project_start
            )

        if run.restricted_to_watch_warning:
            input_conditions.append(relevant_condition)

        input_row_count = session.execute(
            select(func.count())
            .select_from(BestTrackObservation)
            .join(
                Disturbance,
                BestTrackObservation.disturbance_pk == Disturbance.id,
            )
            .where(*input_conditions)
        ).scalar_one()

        eligible_count = session.execute(
            select(
                func.count(
                    func.distinct(BestTrackObservation.disturbance_pk)
                )
            )
            .select_from(BestTrackObservation)
            .join(
                Disturbance,
                BestTrackObservation.disturbance_pk == Disturbance.id,
            )
            .where(*input_conditions)
        ).scalar_one()

        eligible_pks = (
            select(BestTrackObservation.disturbance_pk)
            .join(
                Disturbance,
                BestTrackObservation.disturbance_pk == Disturbance.id,
            )
            .where(*input_conditions)
            .distinct()
        )

        missing_best_track = list(
            session.execute(
                select(Disturbance.disturbance_id)
                .where(
                    relevant_condition,
                    Disturbance.id.not_in(eligible_pks),
                )
                .order_by(Disturbance.disturbance_id)
            ).scalars()
        )

        point_count = session.execute(
            select(func.count())
            .select_from(InterpolatedPoint)
            .where(
                InterpolatedPoint.run_id == interpolation_run_id
            )
        ).scalar_one()

        interpolated_system_count = session.execute(
            select(
                func.count(
                    func.distinct(InterpolatedPoint.disturbance_pk)
                )
            )
            .where(
                InterpolatedPoint.run_id == interpolation_run_id
            )
        ).scalar_one()

        if run.input_row_count != input_row_count:
            raise RuntimeError(
                "Interpolation input row count does not match the database"
            )

        if run.disturbance_count != eligible_count:
            raise RuntimeError(
                "Interpolation disturbance count does not match "
                "the eligible system count"
            )

        if run.output_row_count != point_count:
            raise RuntimeError(
                "Interpolation output row count does not match "
                "the stored point count"
            )

        if interpolated_system_count != eligible_count:
            raise RuntimeError(
                "Not all eligible systems were interpolated"
            )

        return {
            "watch_warning_systems": relevant_count,
            "eligible_systems": eligible_count,
            "missing_best_track": missing_best_track,
            "input_observations": input_row_count,
            "interpolated_systems": interpolated_system_count,
            "interpolated_points": point_count,
        }

def run_data_pipeline(
    *,
    towns_path: Path | None = None,
    best_track_path: Path | None = None,
    step_minutes: int = 15,
    label: str = "data pipeline",
    force_gml: bool = False,
    gml_batch_size: int = DEFAULT_BATCH_FILES,
) -> dict[str, Any]:
    """Run all pipeline stages in dependency order."""
    results: dict[str, Any] = {}

    results["codes"] = _load_codes()

    results["towns"] = _load_town_data(
        towns_path=towns_path,
    )

    results["best_track"] = _load_best_track_data(
        best_track_path=best_track_path,
    )

    results["gml"] = _load_gml_data(
        force=force_gml,
        batch_size=gml_batch_size,
    )

    results["interpolation"] = _run_interpolation(
        step_minutes=step_minutes,
        label=label,
    )

    results["validation"] = _validate_pipeline(
        results["interpolation"]["run_id"],
    )

    return results