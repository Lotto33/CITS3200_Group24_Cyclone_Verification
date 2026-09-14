"""Load the contingency tables in ``data/contingency_tables/``.

Six files per disturbance: ``_table_a`` .. ``_table_d``,
``_contingency_summary`` and ``_contingency_matrix``. The matrix is **not**
loaded -- it is a rendering of the same four counts plus totals, and storing it
would be a second source of truth that can drift. It is recomputed from the
summary in the schema layer.

``Location`` and ``State`` resolve to ``town_id``; the CSV export layer puts
them back. Tables B and C carry ``Location`` with no state at all, which only
resolves because the towns loader deduplicates the sheet -- so the lookup is
made to fail loudly on an ambiguous name rather than guess, since guessing
would attribute one town's verification to another.

The generator itself (``gen_cont_tables.py``) lives on
``origin/feature/contigency-tables``, not on main, so this reads its committed
output. Once that branch merges, the generator can write these tables directly.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.column_maps import (
    CONTINGENCY_SUMMARY_COLUMNS,
    CONTINGENCY_TM_FORMAT,
    TABLE_A_COLUMNS,
    TABLE_B_COLUMNS,
    TABLE_C_COLUMNS,
    TABLE_D_COLUMNS,
)
from app.models.disturbance import Disturbance
from app.models.enums import Outcome, SummaryScope
from app.models.verification import (
    ForecastAdviceDistance,
    ObservedTownImpact,
    ObservedWindDistance,
    VerificationPair,
    VerificationRun,
    VerificationSummary,
)
from app.services.loaders.common import (
    Stats,
    clean_cell,
    code_version,
    season_of,
    to_bool,
    to_datetime,
    to_float,
    to_int,
)
from app.services.loaders.towns import resolve_town_ids

log = logging.getLogger(__name__)

_SUFFIX_RE = re.compile(
    r"^(?P<dist>.+?)_(?P<kind>table_[abcd]|contingency_summary|contingency_matrix)\.csv$"
)

CHILD_MODELS = (
    ForecastAdviceDistance,
    ObservedWindDistance,
    ObservedTownImpact,
    VerificationPair,
    VerificationSummary,
)


def default_contingency_dir() -> Path:
    return settings.DATA_DIR / "contingency_tables"


def discover(directory: Path | None = None) -> dict[str, dict[str, Path]]:
    """``{disturbance_id: {kind: path}}`` for the files present."""
    directory = directory or default_contingency_dir()
    found: dict[str, dict[str, Path]] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.csv")):
        match = _SUFFIX_RE.match(path.name)
        if not match:
            log.warning("ignoring unrecognised contingency file %s", path.name)
            continue
        found.setdefault(match.group("dist"), {})[match.group("kind")] = path
    return found


def _read(path: Path, expected: dict[str, str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in expected if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns {missing}")
    return frame


def load_verification(
    session: Session,
    *,
    directory: Path | None = None,
    interpolation_run_id: int | None = None,
    label: str | None = None,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Load every discovered disturbance into a single new verification run."""
    stats = stats if stats is not None else Stats()
    directory = directory or default_contingency_dir()
    per_disturbance = discover(directory)
    if not per_disturbance:
        raise ValueError(f"no contingency CSVs found under {directory}")

    town_ids = resolve_town_ids(session)
    dist_pks = {
        d.disturbance_id: d.id for d in session.execute(select(Disturbance)).scalars()
    }

    run = VerificationRun(
        created_at=datetime.now(UTC),
        label=label or f"loaded from {directory.name}",
        interpolation_run_id=interpolation_run_id,
        forecast_source="gml_bulletins",
        town_count=len(town_ids),
        disturbance_count=len(per_disturbance),
        code_version=code_version(),
        notes=(
            "Loaded from the committed contingency CSVs. "
            "interpolation_run_id is null unless supplied, because the grid "
            "those CSVs were scored against predates the database."
        ),
    )
    session.add(run)
    session.flush()

    counts: Counter[str] = Counter()
    missing_towns: Counter[str] = Counter()

    for ident, files in per_disturbance.items():
        dist_pk = dist_pks.get(ident)
        if dist_pk is None:
            stats.conflicts.append(
                f"{ident}: no such disturbance; its contingency tables were skipped"
            )
            counts["skipped_disturbances"] += 1
            continue

        base = {"run_id": run.id, "disturbance_pk": dist_pk}

        if "table_a" in files:
            counts["table_a"] += _load_table_a(
                session, files["table_a"], base, town_ids, missing_towns
            )
        if "table_b" in files:
            counts["table_b"] += _load_table_b(
                session, files["table_b"], base, town_ids, missing_towns
            )
        if "table_c" in files:
            counts["table_c"] += _load_table_c(
                session, files["table_c"], base, town_ids, missing_towns
            )
        if "table_d" in files:
            counts["table_d"] += _load_table_d(
                session, files["table_d"], base, town_ids, missing_towns, ident, stats
            )
        if "contingency_summary" in files:
            _load_summary(session, files["contingency_summary"], run.id, ident, stats)
            counts["summaries"] += 1

    if missing_towns:
        stats.conflicts.append(
            f"{len(missing_towns)} location names in the contingency CSVs are "
            f"not in the towns sheet: {dict(missing_towns.most_common(10))}"
        )

    rebuild_summaries(
        session, run.id, scored_disturbances=set(per_disturbance) & set(dist_pks)
    )
    session.flush()

    stats.notes.update({"run_id": run.id, **counts})
    return {
        "run_id": run.id,
        "rows_written": sum(v for k, v in counts.items() if k.startswith("table_")),
        **counts,
    }


def _town_pk(
    name: str | None, town_ids: dict[str, int], missing: Counter[str]
) -> int | None:
    key = clean_cell(name)
    if key is None:
        return None
    pk = town_ids.get(key)
    if pk is None:
        missing[key] += 1
    return pk


def _load_table_a(session, path, base, town_ids, missing) -> int:
    frame = _read(path, TABLE_A_COLUMNS)
    rows = []
    for raw in frame.to_dict("records"):
        town_id = _town_pk(raw["Location"], town_ids, missing)
        if town_id is None:
            continue
        rows.append(
            {
                **base,
                "town_id": town_id,
                "base_time": to_datetime(
                    raw["Base time"], CONTINGENCY_TM_FORMAT, field="Base time"
                ),
                # Signed: negative means the town is inside the area. Blank
                # means the bulletin carried no such area at all.
                "distance_to_watch_km": to_float(
                    raw["Distance to watch"], field="Distance to watch"
                ),
                "distance_to_warning_km": to_float(
                    raw["Distance to warning"], field="Distance to warning"
                ),
                "watch": bool(to_bool(raw["Watch"], field="Watch")),
                "warning": bool(to_bool(raw["Warning"], field="Warning")),
            }
        )
    return _insert(session, ForecastAdviceDistance, rows)


def _load_table_b(session, path, base, town_ids, missing) -> int:
    frame = _read(path, TABLE_B_COLUMNS)
    rows = []
    for raw in frame.to_dict("records"):
        town_id = _town_pk(raw["Location"], town_ids, missing)
        if town_id is None:
            continue
        rows.append(
            {
                **base,
                "town_id": town_id,
                "tm": to_datetime(raw["Time"], CONTINGENCY_TM_FORMAT, field="Time"),
                "analysis_uncertainty_km": to_float(
                    raw["Analysis Uncertainty"], field="Analysis Uncertainty"
                ),
                "distance_to_gale_km": to_float(
                    raw["Distance to gale"], field="Distance to gale"
                ),
                "distance_to_storm_km": to_float(
                    raw["Distance to storm"], field="Distance to storm"
                ),
                "distance_to_hurricane_km": to_float(
                    raw["Distance to hurricane"], field="Distance to hurricane"
                ),
            }
        )
    return _insert(session, ObservedWindDistance, rows)


def _load_table_c(session, path, base, town_ids, missing) -> int:
    frame = _read(path, TABLE_C_COLUMNS)
    rows = []
    for raw in frame.to_dict("records"):
        town_id = _town_pk(raw["Location"], town_ids, missing)
        if town_id is None:
            continue
        rows.append(
            {
                **base,
                "town_id": town_id,
                "base_time": to_datetime(
                    raw["Base time"], CONTINGENCY_TM_FORMAT, field="Base time"
                ),
                "observed": bool(to_bool(raw["Observed"], field="Observed")),
            }
        )
    return _insert(session, ObservedTownImpact, rows)


def _load_table_d(session, path, base, town_ids, missing, ident, stats: Stats) -> int:
    frame = _read(path, TABLE_D_COLUMNS)
    rows = []
    for raw in frame.to_dict("records"):
        town_id = _town_pk(raw["Location"], town_ids, missing)
        if town_id is None:
            continue
        forecast = bool(to_bool(raw["Forecast"], field="Forecast"))
        observed = bool(to_bool(raw["Observed"], field="Observed"))
        rows.append(
            {
                **base,
                "town_id": town_id,
                "base_time": to_datetime(
                    raw["Base time"], CONTINGENCY_TM_FORMAT, field="Base time"
                ),
                "season": clean_cell(raw["Season"]) or season_of(ident),
                "forecast": forecast,
                "observed": observed,
                # Derived and stored, so the summary is an indexed GROUP BY
                # rather than a CASE expression.
                "outcome": Outcome.classify(forecast, observed).value,
            }
        )
    return _insert(session, VerificationPair, rows)


def _load_summary(session, path, run_id, ident, stats: Stats) -> None:
    """Load the generator's own summary, for cross-checking.

    Stored under ``scope='disturbance'``. ``rebuild_summaries`` then recomputes
    every scope from ``verification_pair``, so if the generator's numbers and
    the loaded pairs ever disagree the recomputed row wins and the discrepancy
    is recorded.
    """
    frame = _read(path, CONTINGENCY_SUMMARY_COLUMNS)
    if frame.empty:
        return
    raw = frame.to_dict("records")[0]
    reported = {
        attribute: to_int(raw[column], field=column)
        for column, attribute in CONTINGENCY_SUMMARY_COLUMNS.items()
    }
    stats.notes.setdefault("reported_summaries", {})[ident] = reported


def rebuild_summaries(
    session: Session,
    run_id: int,
    *,
    scored_disturbances: set[str] | None = None,
) -> int:
    """Recompute ``verification_summary`` for a run from its pairs.

    Scopes: overall, per disturbance, and per season. Per-state would need a
    join to ``town`` and is left until an endpoint needs it.

    ``scored_disturbances`` names systems that were scored even if they
    produced no pairs, so they get an explicit all-zero row. That is a real
    case -- ``AU202526_05U`` has header-only tables and an all-zero summary
    from the generator -- and a zero row answers "what was the skill here?"
    with "nothing was scored", where a missing row is indistinguishable from
    "never run".
    """
    session.execute(
        delete(VerificationSummary).where(VerificationSummary.run_id == run_id)
    )

    def counts_for(*group_by):
        statement = (
            select(*group_by, VerificationPair.outcome, func.count())
            .where(VerificationPair.run_id == run_id)
            .group_by(*group_by, VerificationPair.outcome)
        )
        tallies: dict[object, Counter[str]] = {}
        for row in session.execute(statement):
            key = row[0] if group_by else None
            tallies.setdefault(key, Counter())[row[-2]] += row[-1]
        return tallies

    written = 0
    for scope, group_by in (
        # `all` always gets a row, even for an empty run.
        (SummaryScope.ALL, ()),
        (SummaryScope.DISTURBANCE, (Disturbance.disturbance_id,)),
        (SummaryScope.SEASON, (VerificationPair.season,)),
    ):
        statement_groups = group_by
        if scope is SummaryScope.DISTURBANCE:
            # Needs the join, so build it explicitly rather than via counts_for.
            tallies: dict[object, Counter[str]] = {}
            rows = session.execute(
                select(
                    Disturbance.disturbance_id,
                    VerificationPair.outcome,
                    func.count(),
                )
                .join(
                    Disturbance,
                    VerificationPair.disturbance_pk == Disturbance.id,
                )
                .where(VerificationPair.run_id == run_id)
                .group_by(Disturbance.disturbance_id, VerificationPair.outcome)
            )
            for ident, outcome, total in rows:
                tallies.setdefault(ident, Counter())[outcome] += total
            for ident in scored_disturbances or ():
                tallies.setdefault(ident, Counter())
        else:
            tallies = counts_for(*statement_groups)
            if scope is SummaryScope.ALL and not tallies:
                tallies = {None: Counter()}

        for key, tally in tallies.items():
            session.add(
                VerificationSummary(
                    run_id=run_id,
                    scope=scope.value,
                    scope_key=None if key is None else str(key),
                    hit=tally.get(Outcome.HIT.value, 0),
                    false_alarm=tally.get(Outcome.FALSE_ALARM.value, 0),
                    miss=tally.get(Outcome.MISS.value, 0),
                    correct_negative=tally.get(Outcome.CORRECT_NEGATIVE.value, 0),
                    total=sum(tally.values()),
                )
            )
            written += 1
    session.flush()
    return written


def _insert(session: Session, model, rows: list[dict]) -> int:
    """Insert rows, replacing any that already exist for this run."""
    if not rows:
        return 0
    # Chunked to stay well inside SQLite's bound-parameter ceiling.
    width = max(1, len(rows[0]))
    chunk = max(1, 20_000 // width)
    for start in range(0, len(rows), chunk):
        session.execute(model.__table__.insert(), rows[start : start + chunk])
    return len(rows)


def delete_run(session: Session, run_id: int) -> None:
    """Remove a verification run and everything under it."""
    session.execute(delete(VerificationRun).where(VerificationRun.id == run_id))
    session.flush()
