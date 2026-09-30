"""Run the best-track interpolation from the database and store the result.

The science lives in
:mod:`app.services.interpolation.interpolate_best_track` -- the 15-minute grid
and the threshold-aware wind-radius rules that carefully "preserve original
observations exactly, including 0 and NaN". None of that is reimplemented
here. This module only assembles the input frame from
``best_track_observation``, calls those functions, and writes
``interpolated_point`` rows under an ``interpolation_run``.

Reading the input from the database rather than
``data/processed/best_track_interpolation_input.csv`` makes the DB the source
of truth going forward, and means the pipeline no longer depends on a
``data/processed/`` directory that does not exist in a fresh checkout.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.column_maps import INTERPOLATED_COLUMNS
from app.models.best_track import BestTrackObservation
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset
from app.models.interpolation import InterpolatedPoint, InterpolationRun
from app.services.interpolation.interpolate_best_track import (
    MPS_TO_KNOTS,
    RADIUS_THRESHOLDS,
    STEP_MINUTES,
    interpolate_best_track,
)
from app.services.loaders.common import Stats, code_version

log = logging.getLogger(__name__)

#: Matches PROJECT_START in process_best_track.
DEFAULT_PROJECT_START = datetime(2016, 7, 1, tzinfo=UTC)

#: The measurement attributes carried through interpolation, in CSV spelling
#: so the existing functions see the column names they expect.
_RADIUS_ATTRS = [
    attribute
    for column, attribute in INTERPOLATED_COLUMNS.items()
    if column.startswith("MN_RADIUS_")
]
_LINEAR_ATTRS = ["lat", "lon", "position_uncertainty", "max_wind_spd"]
_ATTR_BY_COLUMN = {c: a for c, a in INTERPOLATED_COLUMNS.items()}
_COLUMN_BY_ATTR = {a: c for c, a in INTERPOLATED_COLUMNS.items()}


def build_input_frame(
    session: Session,
    *,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
    project_start: datetime | None = DEFAULT_PROJECT_START,
    watch_warning_only: bool = True,
) -> pd.DataFrame:
    """Assemble the interpolation input, in the CSV's column spelling.

    Mirrors ``process_best_track``: filter to the project period and, by
    default, to disturbances that actually carried a GML watch or warning.
    """
    attributes = ["tm", *_LINEAR_ATTRS, *_RADIUS_ATTRS]
    columns = [
        Disturbance.disturbance_id,
        Disturbance.name,
        BestTrackObservation.disturbance_pk,
        *[getattr(BestTrackObservation, a) for a in attributes],
    ]
    statement = (
        select(*columns)
        .join(Disturbance, BestTrackObservation.disturbance_pk == Disturbance.id)
        .where(BestTrackObservation.dataset == dataset.value)
        .order_by(Disturbance.disturbance_id, BestTrackObservation.tm)
    )
    if project_start is not None:
        statement = statement.where(BestTrackObservation.tm >= project_start)
    if watch_warning_only:
        statement = statement.where(Disturbance.has_watch | Disturbance.has_warning)

    rows = session.execute(statement).mappings().all()
    frame = pd.DataFrame(
        [
            {
                "DISTURBANCE_ID": row["disturbance_id"],
                "NAME": row["name"],
                "_disturbance_pk": row["disturbance_pk"],
                "TM": row["tm"],
                **{_COLUMN_BY_ATTR[a]: row[a] for a in attributes if a != "tm"},
            }
            for row in rows
        ]
    )
    if frame.empty:
        return frame

    # The interpolator does arithmetic on these, and reads TM as a
    # DatetimeIndex. Everything stored is already UTC.
    frame["TM"] = pd.to_datetime(frame["TM"], utc=True)
    for attribute in _LINEAR_ATTRS + _RADIUS_ATTRS:
        column = _COLUMN_BY_ATTR[attribute]
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_interpolation(
    session: Session,
    *,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
    step_minutes: int = STEP_MINUTES,
    project_start: datetime | None = DEFAULT_PROJECT_START,
    watch_warning_only: bool = True,
    label: str | None = None,
    replace: bool = False,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Interpolate and store a new run. Returns row counts.

    With ``replace``, earlier runs carrying the same ``label`` are deleted
    first, so a repeated ``cli all`` leaves one run rather than a pile of
    identical ones.
    """
    stats = stats if stats is not None else Stats()

    if dataset is not TrackDataset.BOM_BEST_TRACK:
        # The OTCR reanalysis ends 2016-12-25 and holds 58 rows inside the
        # project period against best track's 4,383. Interpolating it would
        # produce a near-empty grid that silently looks like a valid result.
        raise ValueError(
            f"{dataset.value} cannot be interpolated: it ends before the "
            "project period is under way. Use bom_best_track."
        )

    frame = build_input_frame(
        session,
        dataset=dataset,
        project_start=project_start,
        watch_warning_only=watch_warning_only,
    )
    if frame.empty:
        raise ValueError(
            "no observations matched: load the best track and the GML "
            "bulletins first (the watch/warning filter needs the bulletins)"
        )

    pk_by_id = frame.groupby("DISTURBANCE_ID")["_disturbance_pk"].first().to_dict()
    interpolated = interpolate_best_track(
        frame.drop(columns=["_disturbance_pk"]), step_minutes=step_minutes
    )

    if replace and label is not None:
        stats.notes["replaced_runs"] = delete_runs_by_label(session, label)

    run = InterpolationRun(
        created_at=datetime.now(UTC),
        label=label,
        source_dataset=dataset.value,
        step_minutes=step_minutes,
        project_start=project_start,
        gf_threshold_kn=RADIUS_THRESHOLDS["GF"],
        sf_threshold_kn=RADIUS_THRESHOLDS["SF"],
        hf_threshold_kn=RADIUS_THRESHOLDS["HF"],
        mps_to_knots=MPS_TO_KNOTS,
        restricted_to_watch_warning=watch_warning_only,
        input_row_count=len(frame),
        output_row_count=len(interpolated),
        disturbance_count=int(frame["DISTURBANCE_ID"].nunique()),
        code_version=code_version(),
    )
    session.add(run)
    session.flush()

    rows = []
    for record in interpolated.to_dict("records"):
        ident = record["DISTURBANCE_ID"]
        row: dict[str, object] = {
            "run_id": run.id,
            "disturbance_pk": pk_by_id[ident],
            "tm": pd.Timestamp(record["TM"]).to_pydatetime(),
            "is_interpolated": bool(record["IS_INTERPOLATED"]),
        }
        for column, attribute in INTERPOLATED_COLUMNS.items():
            if column in {"TM", "IS_INTERPOLATED"}:
                continue
            value = record.get(column)
            # NaN is "unknown"; an explicit 0 is "known absence" and must not
            # be collapsed into it.
            row[attribute] = None if pd.isna(value) else float(value)
        rows.append(row)

    if rows:
        session.execute(InterpolatedPoint.__table__.insert(), rows)
    session.flush()

    stats.notes.update(
        {
            "run_id": run.id,
            "input_rows": len(frame),
            "output_rows": len(rows),
            "disturbances": run.disturbance_count,
            "step_minutes": step_minutes,
        }
    )
    return {
        "run_id": run.id,
        "rows_read": len(frame),
        "rows_written": len(rows),
    }


def delete_run(session: Session, run_id: int) -> int:
    """Remove one interpolation run and its points."""
    deleted = session.execute(
        delete(InterpolationRun).where(InterpolationRun.id == run_id)
    ).rowcount
    session.flush()
    return deleted or 0


def delete_runs_by_label(session: Session, label: str) -> int:
    """Remove every interpolation run with ``label``; points go by cascade."""
    deleted = session.execute(
        delete(InterpolationRun).where(InterpolationRun.label == label)
    ).rowcount
    session.flush()
    return deleted or 0


def latest_run_id(
    session: Session, *, dataset: TrackDataset | None = None
) -> int | None:
    statement = select(InterpolationRun.id).order_by(InterpolationRun.id.desc())
    if dataset is not None:
        statement = statement.where(InterpolationRun.source_dataset == dataset.value)
    return session.execute(statement.limit(1)).scalar_one_or_none()
