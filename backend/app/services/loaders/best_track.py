"""Load ``data/best_track.csv`` into ``disturbance`` + ``best_track_observation``.

Expect 31,706 rows across 1,133 disturbances, TM spanning 1907-01-17 to
2026-04-12.

The CSV is read as text with ``keep_default_na=False`` so that a blank arrives
as ``""`` and an explicit zero as ``"0"``. Most of the 79 columns are blank on
historical rows, and the difference between "no gales in that quadrant" (0) and
"not analysed" (NULL) is one the interpolator depends on, so it must survive
ingest intact.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.column_maps import (
    BEST_TRACK_COLUMNS,
    BEST_TRACK_CSV_HEADER,
    BEST_TRACK_FLOAT_COLUMNS,
    BEST_TRACK_HEADER_ROW,
    BEST_TRACK_TM_FORMAT,
)
from app.db.upsert import upsert_many
from app.models.best_track import BestTrackObservation
from app.models.codes import CodeDomain, CodeValue
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset
from app.services.loaders.codes_seed import CODE_COLUMN_BINDINGS
from app.services.loaders.common import (
    Stats,
    clean_cell,
    is_test_disturbance,
    season_of,
    to_datetime,
    to_float,
    to_int,
)

log = logging.getLogger(__name__)

OBSERVATION_CONFLICT = ("dataset", "disturbance_pk", "tm")


def default_best_track_path() -> Path:
    """``data/best_track.csv``.

    This is BoM product IDCKMSTM0S. The interpolation pipeline's constant
    still names the file ``IDCKMSTM0S.csv``, which does not exist in the
    repository -- same product, different filename.
    """
    return settings.DATA_DIR / "best_track.csv"


def read_best_track_csv(path: Path | None = None) -> pd.DataFrame:
    """Read the CSV as raw strings and verify the header hasn't moved."""
    path = path or default_best_track_path()
    frame = pd.read_csv(
        path,
        skiprows=BEST_TRACK_HEADER_ROW,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    header = tuple(frame.columns)
    if header != BEST_TRACK_CSV_HEADER:
        unexpected = sorted(set(header) - set(BEST_TRACK_CSV_HEADER))
        absent = sorted(set(BEST_TRACK_CSV_HEADER) - set(header))
        raise ValueError(
            f"{path.name} header does not match db.column_maps: "
            f"unexpected={unexpected} missing={absent}"
        )
    return frame


def upsert_disturbances(
    session: Session,
    frame: pd.DataFrame,
    *,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Create or update one ``disturbance`` per DISTURBANCE_ID in ``frame``.

    Returns ``{disturbance_id: pk}`` so the observation loader can resolve its
    foreign keys without a query per row.
    """
    stats = stats if stats is not None else Stats()
    seen: dict[str, dict[str, object]] = {}

    for row in frame.to_dict("records"):
        ident = clean_cell(row["DISTURBANCE_ID"])
        if not ident:
            continue
        name = clean_cell(row["NAME"])
        type_code = clean_cell(row["TYPE"])
        record = seen.setdefault(
            ident,
            {"name": name, "type_code": type_code, "names": set()},
        )
        if name:
            record["names"].add(name)
        record["type_code"] = record["type_code"] or type_code

    # NAME is documented as constant per disturbance; verify rather than trust.
    for ident, record in seen.items():
        if len(record["names"]) > 1:
            stats.conflicts.append(
                f"{ident}: NAME is not constant across its rows "
                f"({sorted(record['names'])}); using the first"
            )

    existing = {
        d.disturbance_id: d
        for d in session.execute(select(Disturbance)).scalars()
    }
    for ident, record in seen.items():
        disturbance = existing.get(ident)
        if disturbance is None:
            disturbance = Disturbance(disturbance_id=ident)
            session.add(disturbance)
        disturbance.name = record["name"]
        disturbance.type_code = record["type_code"]
        disturbance.season = season_of(ident)
        # has_best_track is NOT set here: this function also runs for the OTCR
        # reanalysis, and OTCR covers one system (AU200203_08U) that the BoM
        # best track does not. It is derived from the BoM observation count by
        # refresh_disturbance_observation_stats instead.
        #
        # A GML bulletin may already have marked this as a test product; never
        # clear that flag from here.
        disturbance.is_test = disturbance.is_test or is_test_disturbance(
            ident, record["name"]
        )
    session.flush()

    return {
        d.disturbance_id: d.id
        for d in session.execute(select(Disturbance)).scalars()
    }


def known_code_values(session: Session) -> dict[str, set[str]]:
    """Map observation attribute -> the code values the spec defines for it.

    Used to *report* out-of-spec codes, never to reject them: the shipped CSV
    carries ``PRES_WIND_RELATION_USED = 40`` on 71 rows that the 2011 lookup
    does not list.
    """
    by_domain: dict[str, set[str]] = {}
    for domain_code, code in session.execute(
        select(CodeDomain.code, CodeValue.code).join(
            CodeValue, CodeValue.domain_id == CodeDomain.id
        )
    ):
        by_domain.setdefault(domain_code, set()).add(code)
    return {
        attribute: by_domain.get(domain, set())
        for attribute, domain in CODE_COLUMN_BINDINGS.items()
    }


def build_observation_rows(
    frame: pd.DataFrame,
    pk_by_id: dict[str, int],
    *,
    dataset: TrackDataset,
    ingest_run_id: int | None = None,
    stats: Stats | None = None,
    valid_codes: dict[str, set[str]] | None = None,
) -> list[dict[str, object]]:
    """Coerce ``frame`` into ``best_track_observation`` payload dicts."""
    stats = stats if stats is not None else Stats()
    valid_codes = valid_codes or {}
    rows: list[dict[str, object]] = []

    for offset, raw in enumerate(frame.to_dict("records")):
        # +1 for the header line itself, on top of the skipped metadata lines.
        source_row = BEST_TRACK_HEADER_ROW + 2 + offset

        ident = clean_cell(raw["DISTURBANCE_ID"])
        tm = to_datetime(raw["TM"], BEST_TRACK_TM_FORMAT, field="TM")
        if not ident or tm is None:
            stats.notes.setdefault("rows_without_key", 0)
            stats.notes["rows_without_key"] += 1
            continue

        row: dict[str, object] = {
            "dataset": dataset.value,
            "disturbance_pk": pk_by_id[ident],
            "tm": tm,
            "ingest_run_id": ingest_run_id,
            "source_row_number": source_row,
        }

        for column, attribute in BEST_TRACK_COLUMNS.items():
            if column == "TM":
                continue
            value = raw[column]
            stats.observe(column, value)
            if column in {"TYPE", "COMMENT"}:
                row[attribute] = clean_cell(value)
            elif column in BEST_TRACK_FLOAT_COLUMNS:
                row[attribute] = to_float(value, field=column)
            else:
                row[attribute] = to_int(value, field=column)

            # Report codes the 2011 spec does not define, without failing.
            allowed = valid_codes.get(attribute)
            if allowed and row[attribute] is not None:
                as_code = str(row[attribute])
                if as_code.endswith(".0"):
                    as_code = as_code[:-2]
                if as_code not in allowed:
                    stats.unknown_code[attribute][as_code] += 1

        rows.append(row)

    return rows


def load_best_track(
    session: Session,
    frame: pd.DataFrame,
    *,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
    ingest_run_id: int | None = None,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Upsert disturbances then observations. Idempotent on the natural key."""
    stats = stats if stats is not None else Stats()

    pk_by_id = upsert_disturbances(session, frame, stats=stats)
    rows = build_observation_rows(
        frame,
        pk_by_id,
        dataset=dataset,
        ingest_run_id=ingest_run_id,
        stats=stats,
        valid_codes=known_code_values(session),
    )
    written = upsert_many(
        session,
        BestTrackObservation,
        rows,
        conflict_cols=OBSERVATION_CONFLICT,
    )
    session.flush()
    refresh_disturbance_observation_stats(session, dataset=dataset)
    session.flush()

    stats.notes["observations"] = written
    stats.notes["disturbances"] = len(pk_by_id)
    return {"rows_read": len(frame), "rows_written": written}


def refresh_disturbance_observation_stats(
    session: Session,
    *,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
) -> None:
    """Recompute the denormalised observation counts, TM extent and flag.

    Only the primary dataset drives these, so ingesting the OTCR reanalysis
    neither rewrites a disturbance's best-track extent with reanalysis dates
    nor claims it has a best track when it does not.
    """
    observation_count = (
        select(func.count(BestTrackObservation.id))
        .where(
            BestTrackObservation.disturbance_pk == Disturbance.id,
            BestTrackObservation.dataset == dataset.value,
        )
        .scalar_subquery()
    )
    session.execute(
        Disturbance.__table__.update().values(
            has_best_track=observation_count > 0,
            observation_count=(
                select(func.count(BestTrackObservation.id))
                .where(
                    BestTrackObservation.disturbance_pk == Disturbance.id,
                    BestTrackObservation.dataset == dataset.value,
                )
                .scalar_subquery()
            ),
            first_obs_tm=(
                select(func.min(BestTrackObservation.tm))
                .where(
                    BestTrackObservation.disturbance_pk == Disturbance.id,
                    BestTrackObservation.dataset == dataset.value,
                )
                .scalar_subquery()
            ),
            last_obs_tm=(
                select(func.max(BestTrackObservation.tm))
                .where(
                    BestTrackObservation.disturbance_pk == Disturbance.id,
                    BestTrackObservation.dataset == dataset.value,
                )
                .scalar_subquery()
            ),
        )
    )
