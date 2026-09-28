"""Run the main data processing pipeline in order."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.session import SessionLocal
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

    return results