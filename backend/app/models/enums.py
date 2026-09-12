"""Enumerations shared by the models, loaders and Pydantic schemas.

Storage policy -- two tiers, and the distinction matters:

*Externally sourced* values (``fix_type``, ``track_type``, ``area_type``,
``wind_type``, ``marine_type``, ``kind``, ``symbol``, ``type_code``,
``region``) are stored in plain ``String`` columns, never ``sa.Enum``. BoM can
add a new ``windType`` at any time; a native or CHECK-constrained enum would
abort a 3,448-file ingest on one unrecognised word, and on PostgreSQL
extending it needs ``ALTER TYPE`` -- precisely the migration SQLite cannot
perform. The enums below exist for readable code and for the response
schemas; unexpected values are stored verbatim and reported via
``ingest_run.stats`` (see :func:`app.services.loaders.common.coerce_enum`).

*Internally generated* values (``dataset``, ``outcome``, ``status``,
``scope``) are stored as ``String`` with an explicit ``CheckConstraint`` built
from these enums, because we control every value that can be written.
"""

from enum import StrEnum


class Region(StrEnum):
    """BoM regional office whose GML directory a bulletin came from."""

    NT = "NT"
    QLD = "QLD"
    WA = "WA"


class TrackDataset(StrEnum):
    """Which best-track CSV an observation row came from.

    ``OTCR_REANALYSIS`` is reference data only: it ends 2016-12-25 and
    contributes 58 rows inside the project period against best track's 4,383,
    so it is never the interpolation input or the verification truth.
    """

    BOM_BEST_TRACK = "bom_best_track"
    OTCR_REANALYSIS = "otcr_reanalysis"


class DisturbanceType(StrEnum):
    """BoM ``TYPE`` -- the system's overall classification."""

    DRAFT = "D"
    TROPICAL_CYCLONE = "T"
    EXTRA_TROPICAL = "E"
    TROPICAL_LOW = "L"
    OTHER = "O"
    UNKNOWN = "U"


class TrackType(StrEnum):
    """GML ``tcTrack/trackType``."""

    OBSERVED = "Observed"
    FORECAST = "Forecast"


class FixType(StrEnum):
    """GML ``fixType``, on both ``tcFix`` and ``tcWindArea``."""

    OBSERVED = "Observed"
    CURRENT = "Current"
    FORECAST = "Forecast"


class FixSymbol(StrEnum):
    """GML ``tcFix/symbol``."""

    LOW = "Low"
    CYCLONE = "Cyclone"


class AreaKind(StrEnum):
    """Originating GML element name for a row in ``bulletin_area``."""

    FORECAST = "tcForecastArea"
    WARNING = "tcWarningArea"
    WATCH = "tcWatchArea"
    WIND = "tcWindArea"


class AreaType(StrEnum):
    """GML ``areaType`` (advice areas only; wind areas leave it null)."""

    LIKELY_TRACKS = "Likely Tracks Area"
    WARNING = "Warning Area"
    WATCH = "Watch Area"


class WindType(StrEnum):
    """GML ``tcWindArea/windType`` -- the land-impact wording."""

    DAMAGING = "Damaging"
    DESTRUCTIVE = "Destructive"
    VERY_DESTRUCTIVE = "Very Destructive"


class MarineType(StrEnum):
    """GML ``tcWindArea/marineType`` -- the marine-warning wording."""

    GALE = "Gale"
    STRONG_GALE = "Strong Gale"
    STORM = "Storm"
    HURRICANE = "Hurricane"


class Outcome(StrEnum):
    """2x2 contingency cell for one (town, base time) forecast/observed pair."""

    HIT = "hit"
    FALSE_ALARM = "false_alarm"
    MISS = "miss"
    CORRECT_NEGATIVE = "correct_negative"

    @classmethod
    def classify(cls, forecast: bool, observed: bool) -> "Outcome":
        if forecast and observed:
            return cls.HIT
        if forecast and not observed:
            return cls.FALSE_ALARM
        if observed:
            return cls.MISS
        return cls.CORRECT_NEGATIVE


class SummaryScope(StrEnum):
    """Grouping a ``verification_summary`` row aggregates over."""

    ALL = "all"
    DISTURBANCE = "disturbance"
    SEASON = "season"
    STATE = "state"


class IngestKind(StrEnum):
    """Which loader produced an ``ingest_run``."""

    CODES = "codes"
    TOWNS = "towns"
    BEST_TRACK = "best_track"
    OTCR = "otcr"
    GML = "gml"
    RELEVANT_IDS = "relevant_ids"
    INTERPOLATION = "interpolation"
    VERIFICATION = "verification"


class IngestStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"


def values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """Member values, for building CheckConstraints."""
    return tuple(m.value for m in enum_cls)


def sql_in_clause(column: str, enum_cls: type[StrEnum]) -> str:
    """``"col IN ('a', 'b')"`` for a CheckConstraint over an internal enum."""
    rendered = ", ".join(f"'{v}'" for v in values(enum_cls))
    return f"{column} IN ({rendered})"
