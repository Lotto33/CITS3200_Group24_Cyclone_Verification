"""GML bulletins: the operational forecast products being verified.

Source: ``data/{NT,QLD,WA}_GMLs/**/*.gml`` -- 3,448 BoM ``tcData`` bulletins,
namespace ``http://www.bom.gov.au/dtd/tc`` with GML 2 geometry.

Geometry is stored as GeoJSON in a JSON column because the producer
(:func:`app.gml_to_geojson.build_feature_collection`) and both consumers (the
Leaflet viewer and the contingency generator) already speak GeoJSON, so there
is no conversion at either end. Nothing ever filters *inside* that JSON --
SQLite offers no usable JSON operators through SQLAlchemy's generic layer --
so all filtering goes through the denormalised ``bbox_*`` and ``vertex_count``
columns, which is exactly why those are NOT NULL. Both geometry columns are
deferred so an ordinary ``select()`` cannot accidentally drag hundreds of MB
through the ORM.

Only ``tcTrack`` and ``tcFix`` appear in every bulletin; every other section is
optional, so each relationship must tolerate zero rows.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.columns import GeoJSONType, UtcDateTime
from app.models.disturbance import Disturbance

#: All GML geometry carries srsName urn:ogc:def:crs:EPSG:6.6:4283, i.e. GDA94 --
#: *not* WGS84/4326. Coordinates are stored as-is rather than reprojected: the
#: offset is around a metre, immaterial to town distances measured in hundreds
#: of kilometres, but it must be recorded rather than assumed.
DEFAULT_SRS = "EPSG:4283"


class Bulletin(TimestampMixin, Base):
    __tablename__ = "bulletin"
    __table_args__ = (
        # The real idempotency key. Note that (disturbance_pk, fcast_time) is
        # NOT unique: more than one regional office can issue for the same
        # system at the same fcastTime.
        UniqueConstraint("source_file"),
        Index("ix_bulletin_disturbance_pk_fcast_time", "disturbance_pk", "fcast_time"),
        Index("ix_bulletin_region", "region"),
        Index("ix_bulletin_issue_time", "issue_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[str] = mapped_column(
        String(8), nullable=False, doc="NT/QLD/WA, from the source directory."
    )
    source_file: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Path relative to data/, e.g. "
        "'NT_GMLs/productfile.20170217.1055.104166905.IDD65401.gml'.",
    )
    product_id: Mapped[str | None] = mapped_column(
        String(16),
        doc="BoM product code parsed from the filename, e.g. IDD65401, "
        "IDQ65248, IDW60266.",
    )
    dist_name_raw: Mapped[str | None] = mapped_column(
        String(60),
        doc="distName exactly as the bulletin spelt it: a cyclone name, "
        "'Tropical Low', or a test marker like 'TEST-WA-2023'.",
    )

    fcast_time: Mapped[datetime | None] = mapped_column(
        UtcDateTime, doc="Nominal analysis / base time."
    )
    issue_time: Mapped[datetime | None] = mapped_column(
        UtcDateTime, doc="When the bulletin was issued."
    )
    expiry_hrs: Mapped[float | None] = mapped_column(
        Float, doc="Validity window in hours; observed values 2, 4, 7, 8."
    )

    srs: Mapped[str] = mapped_column(String(16), nullable=False, default=DEFAULT_SRS)
    bbox_min_lon: Mapped[float | None] = mapped_column(Float)
    bbox_min_lat: Mapped[float | None] = mapped_column(Float)
    bbox_max_lon: Mapped[float | None] = mapped_column(Float)
    bbox_max_lat: Mapped[float | None] = mapped_column(Float)

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        doc="sha256 of the source file, so re-ingest can skip unchanged "
        "bulletins instead of reparsing 487 MB of XML.",
    )
    ingest_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingest_run.id", ondelete="SET NULL")
    )

    disturbance: Mapped[Disturbance] = relationship(back_populates="bulletins")
    tracks: Mapped[list["BulletinTrack"]] = relationship(
        back_populates="bulletin", cascade="all, delete-orphan", passive_deletes=True
    )
    fixes: Mapped[list["BulletinFix"]] = relationship(
        back_populates="bulletin", cascade="all, delete-orphan", passive_deletes=True
    )
    areas: Mapped[list["BulletinArea"]] = relationship(
        back_populates="bulletin", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Bulletin {self.id} {self.region} {self.fcast_time}>"


class BulletinTrack(Base):
    """A ``tcTrack`` LineString: the observed or forecast centre path."""

    __tablename__ = "bulletin_track"
    __table_args__ = (
        Index("ix_bulletin_track_bulletin_id_track_type", "bulletin_id", "track_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bulletin_id: Mapped[int] = mapped_column(
        ForeignKey("bulletin.id", ondelete="CASCADE"), nullable=False
    )
    track_type: Mapped[str | None] = mapped_column(
        String(16), doc="Observed or Forecast. See enums.TrackType."
    )
    start_time: Mapped[datetime | None] = mapped_column(UtcDateTime)
    end_time: Mapped[datetime | None] = mapped_column(UtcDateTime)

    geometry: Mapped[dict[str, Any]] = mapped_column(
        GeoJSONType,
        nullable=False,
        deferred=True,
        doc="GeoJSON LineString.",
    )
    vertex_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_min_lon: Mapped[float | None] = mapped_column(Float)
    bbox_min_lat: Mapped[float | None] = mapped_column(Float)
    bbox_max_lon: Mapped[float | None] = mapped_column(Float)
    bbox_max_lat: Mapped[float | None] = mapped_column(Float)

    bulletin: Mapped[Bulletin] = relationship(back_populates="tracks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BulletinTrack {self.track_type} n={self.vertex_count}>"


class BulletinFix(Base):
    """A ``tcFix`` Point: one dated centre position.

    Coordinates are real columns rather than JSON -- a fix is two floats, and
    these are the values the verification actually filters and measures from.
    """

    __tablename__ = "bulletin_fix"
    __table_args__ = (
        CheckConstraint(
            "lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180",
            name="coords_in_range",
        ),
        Index("ix_bulletin_fix_bulletin_id_fix_time", "bulletin_id", "fix_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bulletin_id: Mapped[int] = mapped_column(
        ForeignKey("bulletin.id", ondelete="CASCADE"), nullable=False
    )
    fix_type: Mapped[str | None] = mapped_column(
        String(16), doc="Observed, Current or Forecast. See enums.FixType."
    )
    fix_time: Mapped[datetime | None] = mapped_column(UtcDateTime)
    symbol: Mapped[str | None] = mapped_column(
        String(32), doc="Low or Cyclone. See enums.FixSymbol."
    )
    category: Mapped[int | None] = mapped_column(
        SmallInteger,
        doc="Australian TC category 1-5. The GML writes an empty "
        "self-closing <category /> when not applicable, which becomes NULL "
        "here -- never 0.",
    )
    time_offset_hours: Mapped[float | None] = mapped_column(
        Float,
        doc="Signed hours relative to the bulletin fcastTime; observed down "
        "to -147 for historical fixes.",
    )
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)

    bulletin: Mapped[Bulletin] = relationship(back_populates="fixes")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BulletinFix {self.fix_type} {self.fix_time}>"


class BulletinArea(Base):
    """A polygon area: watch, warning, likely-tracks, or wind extent.

    One polymorphic table discriminated by ``kind``, mirroring the single
    ``areas[]`` collection the existing parser emits. A wind area leaves
    ``area_type``/``extent`` null; an advice area leaves
    ``wind_type``/``marine_type`` null. Splitting this into two tables would
    duplicate the geometry handling for no query benefit.

    Geometry is always a GeoJSON MultiPolygon, even for a single polygon, so
    every row has one shape; holes are simply the rings after the first.
    Individual rings are deliberately not normalised into their own table --
    nothing queries a ring, and it would multiply the row count five- to
    tenfold.
    """

    __tablename__ = "bulletin_area"
    __table_args__ = (
        Index("ix_bulletin_area_bulletin_id_kind", "bulletin_id", "kind"),
        Index("ix_bulletin_area_kind_fix_time", "kind", "fix_time"),
        Index(
            "ix_bulletin_area_bbox",
            "bbox_min_lon",
            "bbox_min_lat",
            "bbox_max_lon",
            "bbox_max_lat",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bulletin_id: Mapped[int] = mapped_column(
        ForeignKey("bulletin.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        doc="Originating GML element: tcForecastArea, tcWarningArea, "
        "tcWatchArea or tcWindArea. See enums.AreaKind.",
    )

    # Advice areas (tcForecastArea / tcWarningArea / tcWatchArea)
    area_type: Mapped[str | None] = mapped_column(
        String(40), doc="Likely Tracks Area, Warning Area, Watch Area."
    )
    extent: Mapped[str | None] = mapped_column(
        Text,
        doc="Free-text extent, e.g. 'Port McArthur to NT/Qld Border' or 'Up "
        "to 72 hours'; warning-area extents can run to full paragraphs (observed "
        "up to ~800 chars), hence unbounded rather than a fixed VARCHAR. At "
        "least one bulletin contains mojibake here, so read the GML bytes and "
        "let the XML declaration decide the encoding.",
    )

    # Wind areas (tcWindArea)
    wind_type: Mapped[str | None] = mapped_column(
        String(24), doc="Damaging, Destructive, Very Destructive."
    )
    marine_type: Mapped[str | None] = mapped_column(
        String(24), doc="Gale, Strong Gale, Storm, Hurricane."
    )
    fix_type: Mapped[str | None] = mapped_column(String(16))
    fix_time: Mapped[datetime | None] = mapped_column(UtcDateTime)

    geometry: Mapped[dict[str, Any]] = mapped_column(
        GeoJSONType,
        nullable=False,
        deferred=True,
        doc="GeoJSON MultiPolygon.",
    )
    polygon_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ring_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vertex_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Total vertices across every ring. Lets the API budget a response "
        "without loading any geometry.",
    )
    bbox_min_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_lat: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lon: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_lat: Mapped[float] = mapped_column(Float, nullable=False)

    bulletin: Mapped[Bulletin] = relationship(back_populates="areas")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BulletinArea {self.kind} {self.area_type or self.wind_type}>"
