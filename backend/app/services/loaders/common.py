"""Shared loader helpers: value coercion, enum tolerance, run bookkeeping.

The coercion rules here are the reason every loader reads its CSVs with
``dtype=str, keep_default_na=False``. That makes a blank arrive as ``""`` and a
zero as ``"0"`` -- two distinguishable strings. The default ``read_csv`` path
turns an integer column containing blanks into float64 with ``NaN``, and any
later ``fillna(0)`` or ``astype`` collapses the two irreversibly. In this data
``0`` means "known to be zero" (no gales in that quadrant, no eye) while
``NULL`` means "not analysed", and
:mod:`app.services.interpolation.interpolate_best_track` branches on exactly
that difference.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import IngestKind, IngestStatus
from app.models.ingest import IngestRun

log = logging.getLogger(__name__)

#: BoM writes missing values in these CSVs as a single space, not an empty
#: field, so everything strips before testing for blank.
_BLANKS = {"", "-", "nan", "NaN", "None", "null", "NULL"}

_DISTURBANCE_ID_RE = re.compile(r"^AU(\d{4})(\d{2})?_(\d{2})([A-Z])$")
_TEST_ID_SUFFIXES = ("_97U", "_98U", "_99U")


def clean_cell(value: Any) -> str | None:
    """Strip ``value`` and return None if it is blank."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _BLANKS else text


def to_float(value: Any, *, field: str = "") -> float | None:
    """Blank -> None; anything else -> float, or raise."""
    text = clean_cell(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"{field or 'value'}: cannot read {text!r} as a number"
        ) from exc


def to_int(value: Any, *, field: str = "") -> int | None:
    """Blank -> None; an integral value -> int.

    A fractional value raises rather than truncating: every column typed as
    Integer is integral across all 31,706 rows of the shipped CSV, so a
    fraction means the source changed and silence would lose data.
    """
    number = to_float(value, field=field)
    if number is None:
        return None
    if number != int(number):
        raise ValueError(
            f"{field or 'value'}: {number!r} is fractional but the column is "
            "an integer; the source data may have changed"
        )
    return int(number)


def to_bool(value: Any, *, field: str = "") -> bool | None:
    """Parse the several boolean spellings these files use.

    The contingency CSVs are written by pandas and so contain the Python
    literals ``True``/``False``; the towns sheet uses Yes/No and 1/0.
    """
    if isinstance(value, bool):
        return value
    text = clean_cell(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"true", "t", "yes", "y", "1", "1.0"}:
        return True
    if lowered in {"false", "f", "no", "n", "0", "0.0"}:
        return False
    raise ValueError(f"{field or 'value'}: cannot read {text!r} as a boolean")


def to_datetime(value: Any, fmt: str, *, field: str = "") -> datetime | None:
    """Parse with an explicit format and attach UTC.

    The format is always explicit: ``best_track.csv`` writes
    ``YYYY-MM-DD HH:MM`` while the OTCR export writes ``DD/MM/YYYY H:MM``, and
    inference would read ``03/11/2016`` as 11 March.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = clean_cell(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, fmt).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(
            f"{field or 'value'}: {text!r} does not match format {fmt!r}"
        ) from exc


class Stats:
    """Accumulates what a loader learned, for ``ingest_run.stats``."""

    def __init__(self) -> None:
        self.blank_counts: Counter[str] = Counter()
        self.zero_counts: Counter[str] = Counter()
        self.unknown_enum: dict[str, Counter[str]] = defaultdict(Counter)
        self.unknown_code: dict[str, Counter[str]] = defaultdict(Counter)
        self.conflicts: list[str] = []
        self.notes: dict[str, Any] = {}

    def observe(self, field: str, raw: Any) -> None:
        """Record whether ``raw`` was blank or an explicit zero."""
        text = clean_cell(raw)
        if text is None:
            self.blank_counts[field] += 1
        elif text in {"0", "0.0", "-0"}:
            self.zero_counts[field] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "blank_counts": dict(self.blank_counts),
            "zero_counts": dict(self.zero_counts),
            "unknown_enum": {k: dict(v) for k, v in self.unknown_enum.items()},
            "unknown_code": {k: dict(v) for k, v in self.unknown_code.items()},
            "conflicts": self.conflicts,
            **self.notes,
        }


def coerce_enum(
    value: Any,
    enum_cls: type[StrEnum],
    *,
    field: str,
    stats: Stats | None = None,
) -> str | None:
    """Return ``value`` verbatim, recording it if it is not a known member.

    Deliberately never raises. BoM can add a new ``windType`` at any time and a
    single novel bulletin must not abort a 3,448-file ingest, so unrecognised
    values are stored as-is and surfaced through ``ingest_run.stats`` for
    review. Matching is case-insensitive but the original casing is kept.
    """
    text = clean_cell(value)
    if text is None:
        return None
    known = {member.value.casefold(): member.value for member in enum_cls}
    if text.casefold() not in known:
        if stats is not None:
            stats.unknown_enum[field][text] += 1
        log.warning("unrecognised %s value %r (stored verbatim)", field, text)
    return text


def season_of(disturbance_id: str) -> str | None:
    """Derive the cyclone season from a disturbance id.

    ``AU201617_19U`` -> ``2016-17``. Southern-Hemisphere seasons straddle the
    calendar year, which is why the id encodes both halves and why this reads
    the id rather than the observation date -- a single system can have
    observations on both sides of 1 January.

    The four-digit form ``AU2020_97U`` appears among BoM's test products; it
    carries only one year, so it maps to ``2020-21``.
    """
    match = _DISTURBANCE_ID_RE.match((disturbance_id or "").strip())
    if not match:
        return None
    first, second, _, _ = match.groups()
    if second is not None:
        return f"{first}-{second}"
    start = int(first)
    return f"{start}-{(start + 1) % 100:02d}"


def is_test_disturbance(disturbance_id: str, name: str | None = None) -> bool:
    """True for BoM test products rather than real systems."""
    ident = (disturbance_id or "").strip().upper()
    if ident.endswith(_TEST_ID_SUFFIXES):
        return True
    return (name or "").strip().upper().startswith("TEST-")


def code_version() -> str | None:
    """Short git revision, for run provenance. None outside a checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None


@contextmanager
def ingest_run(
    session: Session,
    kind: IngestKind,
    *,
    source: str | None = None,
) -> Iterator[IngestRun]:
    """Open an ``ingest_run`` row, and close it ok/failed on the way out."""
    run = IngestRun(
        created_at=datetime.now(UTC),
        kind=kind.value,
        source=source,
        status=IngestStatus.RUNNING.value,
        code_version=code_version(),
    )
    session.add(run)
    session.commit()
    try:
        yield run
    except Exception as exc:
        session.rollback()
        run.status = IngestStatus.FAILED.value
        run.error = f"{type(exc).__name__}: {exc}"[:4000]
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        raise
    else:
        run.status = IngestStatus.OK.value
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
