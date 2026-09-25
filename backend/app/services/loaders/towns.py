"""Load the TC Locations sheet into ``town`` + ``town_group_membership``.

The sheet has 472 rows but only 466 distinct locations: six QLD entries --
Bamaga, Carmila, Hayman Is, QLD/NSW Border, Sandy Cape and Thursday Is --
appear twice at identical coordinates, once in ``qld_towns`` and once in
``qld_coastal_threat_area_locations``. They are one place in two groups, so the
group becomes a membership row and ``coastal_order`` lives there: Bamaga is 81
in ``qld_towns`` and null in the threat-area group.

Deduplicating matters beyond tidiness. Contingency tables B and C identify a
location by name alone, with no state column, so a name has to resolve to
exactly one town.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.column_maps import TOWN_COLUMNS, TOWN_SHEET_NAME
from app.models.town import Town, TownGroupMembership
from app.services.loaders.common import Stats, clean_cell, to_bool, to_float

log = logging.getLogger(__name__)


def default_towns_path() -> Path:
    return settings.DATA_DIR / "towns.xlsx"


def read_towns_sheet(path: Path | None = None) -> pd.DataFrame:
    """Read the sheet as text, so blanks stay distinguishable from zeros."""
    path = path or default_towns_path()
    frame = pd.read_excel(path, sheet_name=TOWN_SHEET_NAME, dtype=str)
    missing = [c for c in TOWN_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            f"{path.name} sheet {TOWN_SHEET_NAME!r} is missing columns: {missing}"
        )
    return frame


def load_towns(
    session: Session,
    frame: pd.DataFrame,
    *,
    stats: Stats | None = None,
) -> dict[str, int]:
    """Upsert towns and their group memberships from ``frame``.

    Idempotent: keyed on ``(name, state)`` and ``(town_id, town_group)``.
    """
    stats = stats if stats is not None else Stats()
    counts = {"rows_read": 0, "skipped": 0, "towns": 0, "memberships": 0}

    # Collapse the sheet to one record per (name, state), collecting groups.
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for position, row in enumerate(frame.to_dict("records"), start=2):
        counts["rows_read"] += 1
        name = clean_cell(row[_col("Name")])
        state = clean_cell(row[_col("State")])
        lat = to_float(row[_col("Latitude")], field="Latitude")
        lon = to_float(row[_col("Longitude")], field="Longitude")

        # The sheet has formatted-but-empty trailing rows, so a skip count in
        # the hundreds is expected rather than an error.
        if not name or lat is None or lon is None:
            counts["skipped"] += 1
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            log.warning(
                "row %d: %s has out-of-range coords %s,%s",
                position,
                name,
                lat,
                lon,
            )
            counts["skipped"] += 1
            continue

        state = state or ""
        group = clean_cell(row[_col("Town Group")])

        # Whether this row is the first for its location decides whether a
        # differing flag is a real disagreement or just the default being
        # filled in for the first time.
        key = (name, state)
        is_first_row = key not in records
        record = records.setdefault(
            key,
            {
                "name": name,
                "state": state,
                "lat": lat,
                "lon": lon,
                "is_major": False,
                "is_island": False,
                "groups": {},
            },
        )

        # A duplicate entry should agree on position; flag it if it does not.
        if abs(record["lat"] - lat) > 1e-6 or abs(record["lon"] - lon) > 1e-6:
            stats.conflicts.append(
                f"{name} ({state}): coordinates differ between sheet rows "
                f"({record['lat']},{record['lon']}) vs ({lat},{lon})"
            )

        # Flags are OR-ed across the duplicate rows, and a genuine
        # disagreement between them is recorded rather than resolved
        # silently: Sandy Cape really is island=True in the threat-area group
        # and island=False in qld_towns.
        for flag, column in (("is_major", "Major Town"), ("is_island", "Island Town")):
            value = to_bool(row[_col(column)], field=column) or False
            if not is_first_row and record[flag] != value:
                stats.conflicts.append(
                    f"{name} ({state}): {column} differs between sheet rows "
                    f"({record[flag]} vs {value}); taking the OR"
                )
            record[flag] = record[flag] or value

        if group:
            # Float, not int: fractional values are meaningful here.
            record["groups"][group] = to_float(
                row[_col("Coastal Order")], field="Coastal Order"
            )

    # One read, one flush, one read: per-town flushes and membership queries
    # cost two round trips per town, which dominates on a remote server.
    existing = {(t.name, t.state): t for t in session.execute(select(Town)).scalars()}
    towns: dict[tuple[str, str], Town] = {}
    for (name, state), record in records.items():
        town = existing.get((name, state))
        if town is None:
            town = Town(name=name, state=state)
            session.add(town)
        town.lat = record["lat"]
        town.lon = record["lon"]
        town.is_major = record["is_major"]
        town.is_island = record["is_island"]
        towns[(name, state)] = town
        counts["towns"] += 1
    session.flush()

    current = {
        (m.town_id, m.town_group): m
        for m in session.execute(select(TownGroupMembership)).scalars()
    }
    for key, record in records.items():
        town = towns[key]
        for group, order in record["groups"].items():
            membership = current.get((town.id, group))
            if membership is None:
                membership = TownGroupMembership(town_id=town.id, town_group=group)
                session.add(membership)
            membership.coastal_order = order
            counts["memberships"] += 1

    session.flush()
    stats.notes["distinct_towns"] = counts["towns"]
    stats.notes["memberships"] = counts["memberships"]
    stats.notes["skipped_rows"] = counts["skipped"]
    return counts


def _col(header: str) -> str:
    """The sheet column for a mapped header (identity, but explicit)."""
    if header not in TOWN_COLUMNS:
        raise KeyError(f"{header!r} is not in TOWN_COLUMNS")
    return header


def resolve_town_ids(session: Session) -> dict[str, int]:
    """Map town name -> id, raising if any name is ambiguous.

    Contingency tables B and C carry ``Location`` with no state, so this has to
    be unambiguous. It is, after the deduplication above -- but a future sheet
    could add a genuine name collision across states, and guessing would
    silently attribute one town's verification to another.
    """
    by_name: dict[str, list[Town]] = {}
    for town in session.execute(select(Town)).scalars():
        by_name.setdefault(town.name, []).append(town)

    ambiguous = {
        name: sorted(t.state for t in towns)
        for name, towns in by_name.items()
        if len(towns) > 1
    }
    if ambiguous:
        raise ValueError(
            "town names are ambiguous, so a Location-only lookup cannot be "
            f"resolved: {ambiguous}"
        )
    return {name: towns[0].id for name, towns in by_name.items()}
