"""Load the OTCR reanalysis CSV as reference data.

``data/OTCR_alldata_final_external.csv`` -- Objective Tropical Cyclone
Reanalysis 1981-2016, 221 columns, 14,256 rows.

**This is reference data only.** It ends 2016-12-25, so it contributes 58 rows
inside the project period against best track's 4,383, and it covers just one
of the 136 disturbances that have GML bulletins. It is never the interpolation
input and never the verification truth; it exists in the database so the two
analyses can be compared.

Two traps this loader is built around:

* Columns 0-83 are the best-track schema with five OTCR-derived columns
  *interleaved*, so a BoM column is **not** at the same index as in
  ``best_track.csv``. Columns 84-220 are an analyst-workbook dump of per-method
  blocks whose headers repeat -- ``Lat``, ``Lon``, ``Date`` and ``Vmax (kn)``
  each appear four to six times -- so pandas silently renames them ``Lat.1``,
  ``Lat.2`` and so on. Everything here therefore selects **by position** and
  stops after column 84.
* ``TM`` is ``DD/MM/YYYY H:MM`` here, not ``YYYY-MM-DD HH:MM``. Format
  inference would read ``03/11/2016`` as 11 March.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.column_maps import (
    BEST_TRACK_COLUMNS,
    BEST_TRACK_FLOAT_COLUMNS,
    OTCR_EXTRA_COLUMNS,
    OTCR_EXTRA_HEADERS,
    OTCR_HEADER_ROW,
    OTCR_LAST_MAPPED_INDEX,
    OTCR_TM_FORMAT,
)
from app.db.upsert import upsert_many
from app.models.best_track import BestTrackObservation
from app.models.enums import TrackDataset
from app.services.loaders.best_track import (
    OBSERVATION_CONFLICT,
    known_code_values,
    refresh_disturbance_observation_stats,
    upsert_disturbances,
)
from app.services.loaders.common import (
    Stats,
    clean_cell,
    to_datetime,
    to_float,
)

log = logging.getLogger(__name__)


def default_otcr_path() -> Path:
    return settings.DATA_DIR / "OTCR_alldata_final_external.csv"


def read_otcr_csv(path: Path | None = None) -> pd.DataFrame:
    """Read columns 0-84 by position, with the original header text.

    ``header=None`` plus ``skiprows`` keeps pandas from deduplicating the
    repeated names, and ``usecols`` of integers means a shifted column can
    never be read as the wrong field.
    """
    path = path or default_otcr_path()
    raw_header = pd.read_csv(
        path,
        nrows=0,
        header=OTCR_HEADER_ROW,
        dtype=str,
        keep_default_na=False,
    )
    header = list(raw_header.columns)

    # A re-exported workbook with inserted columns must fail loudly rather
    # than write wind speeds into pressure fields.
    for index, expected in OTCR_EXTRA_HEADERS.items():
        actual = header[index] if index < len(header) else "<missing>"
        if actual.strip() != expected:
            raise ValueError(
                f"{path.name} column {index} is {actual!r}, expected "
                f"{expected!r}; the OTCR export layout has changed and "
                "db.column_maps.OTCR_EXTRA_COLUMNS needs revisiting"
            )

    keep = list(range(0, OTCR_LAST_MAPPED_INDEX + 1))
    frame = pd.read_csv(
        path,
        skiprows=OTCR_HEADER_ROW + 1,
        header=None,
        usecols=keep,
        names=keep,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    # Re-label by position using the *original* header text, so the BoM
    # columns can be looked up by name from here on without pandas' mangling.
    frame.columns = [header[i].strip() for i in keep]
    return frame


def load_otcr(
    session: Session,
    frame: pd.DataFrame,
    *,
    ingest_run_id: int | None = None,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Upsert OTCR rows under ``dataset='otcr_reanalysis'``."""
    stats = stats if stats is not None else Stats()
    dataset = TrackDataset.OTCR_REANALYSIS

    pk_by_id = upsert_disturbances(session, frame, stats=stats)
    valid_codes = known_code_values(session)
    columns = list(frame.columns)
    rows: list[dict[str, object]] = []

    for offset, raw in enumerate(frame.to_dict("records")):
        ident = clean_cell(raw["DISTURBANCE_ID"])
        tm = to_datetime(raw["TM"], OTCR_TM_FORMAT, field="TM")
        if not ident or tm is None:
            stats.notes["rows_without_key"] = (
                stats.notes.get("rows_without_key", 0) + 1
            )
            continue

        row: dict[str, object] = {
            "dataset": dataset.value,
            "disturbance_pk": pk_by_id[ident],
            "tm": tm,
            "ingest_run_id": ingest_run_id,
            "source_row_number": OTCR_HEADER_ROW + 2 + offset,
        }

        for column, attribute in BEST_TRACK_COLUMNS.items():
            if column == "TM":
                continue
            if column not in raw:
                # The OTCR export omits nothing today, but be explicit rather
                # than writing a silent NULL if that ever changes.
                row[attribute] = None
                continue
            value = raw[column]
            stats.observe(column, value)
            if column in {"TYPE", "COMMENT"}:
                row[attribute] = clean_cell(value)
            elif column in BEST_TRACK_FLOAT_COLUMNS:
                row[attribute] = to_float(value, field=column)
            else:
                row[attribute] = _lenient_int(value, field=column, stats=stats)

            allowed = valid_codes.get(attribute)
            if allowed and row[attribute] is not None:
                as_code = str(row[attribute]).removesuffix(".0")
                if as_code not in allowed:
                    stats.unknown_code[attribute][as_code] += 1

        # The five interleaved extras plus Adjusted Vm, read by position.
        for index, attribute in OTCR_EXTRA_COLUMNS.items():
            header = columns[index]
            row[attribute] = to_float(raw[header], field=header)

        rows.append(row)

    written = upsert_many(
        session,
        BestTrackObservation,
        rows,
        conflict_cols=OBSERVATION_CONFLICT,
    )
    session.flush()
    # Deliberately recomputed for the BoM dataset only, so ingesting the
    # reanalysis cannot overwrite a disturbance's best-track extent with
    # reanalysis dates.
    refresh_disturbance_observation_stats(
        session, dataset=TrackDataset.BOM_BEST_TRACK
    )
    session.flush()

    stats.notes["observations"] = written
    return {"rows_read": len(frame), "rows_written": written}


def _lenient_int(value: object, *, field: str, stats: Stats) -> int | None:
    """Like ``to_int``, but records a fractional value as NULL instead of raising.

    Strictness is right for ``best_track.csv``, which BoM generates. This file
    is a hand-maintained analyst workbook and has at least one column whose
    contents no longer match its header: ``MAX_REP_TIDE_ANOM_METHOD`` holds 105
    fractional values between 0.13 and 0.72 -- evidently some ratio -- against
    only 15 integers. Those cannot be method codes.

    Such a value is dropped to NULL and counted in
    ``ingest_run.stats['unknown_code']`` rather than stored. Keeping the float
    would work on SQLite, which types loosely, and then fail on PostgreSQL the
    first time this ran there; and writing a ratio into a code column would be
    wrong on any backend. This is reference data, so reporting beats aborting a
    14,256-row load.
    """
    number = to_float(value, field=field)
    if number is None:
        return None
    if number != int(number):
        stats.unknown_code[f"{field} (fractional, dropped)"][str(number)] += 1
        return None
    return int(number)


__all__ = ["default_otcr_path", "read_otcr_csv", "load_otcr"]
