"""Custom SQLAlchemy column types shared across the models."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import JSON

# GeoJSON geometry objects (LineString / MultiPolygon) as produced by
# app/gml_to_geojson.py. Stored as JSON so it round-trips into the map viewers
# with no conversion; JSONB on PostgreSQL.
#
# Nothing ever filters *inside* this column -- SQLite offers no usable JSON
# operators through SQLAlchemy's generic layer. All filtering goes through the
# denormalised bbox_* / vertex_count columns instead, which is exactly why
# those are NOT NULL.
GeoJSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")

# Free-form provenance / parameter payloads.
JSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")


class UtcDateTime(TypeDecorator):
    """A timezone-aware ``DateTime`` that is always UTC.

    SQLite discards ``tzinfo`` entirely, so a naive value written on SQLite and
    an aware value written on PostgreSQL would compare differently and raise
    ``TypeError: can't compare offset-naive and offset-aware datetimes``. This
    normalises at the boundary: convert to UTC and strip ``tzinfo`` on the way
    in, re-attach ``timezone.utc`` on the way out.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        return dialect.type_descriptor(DateTime(timezone=False))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            # Accept ISO-8601 so query parameters and ad-hoc filters work
            # naturally. Anything else is rejected rather than guessed at.
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exc:
                raise TypeError(
                    f"expected a datetime or an ISO-8601 string, got {value!r}"
                ) from exc
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        if dialect.name == "postgresql":
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        return value.replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
