"""Response models for GML bulletins.

The summary models deliberately carry **no geometry**: the corpus holds 20.4
million area vertices, and a per-cyclone dump of them runs to megabytes.
Geometry is opt-in per route, and ``vertex_count`` lets a route budget a
response without loading any of it.

``geometry`` is typed as a plain ``dict`` rather than a nested GeoJSON model on
purpose -- re-validating tens of thousands of floats per request is a real cost
for no benefit, since the values were validated on ingest.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.common import BBox


class BulletinSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    disturbance_id: str | None = None
    region: str
    source_file: str
    product_id: str | None
    dist_name_raw: str | None
    fcast_time: datetime | None
    issue_time: datetime | None
    expiry_hrs: float | None
    srs: str
    bbox: BBox | None = None
    track_count: int = 0
    fix_count: int = 0
    area_count: int = 0
    vertex_count: int = 0


class BulletinTrackRead(BaseModel):
    """Tracks include geometry: a centre path is tens of vertices, not thousands."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    track_type: str | None
    start_time: datetime | None
    end_time: datetime | None
    vertex_count: int
    geometry: dict[str, Any] | None = None


class BulletinFixRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fix_type: str | None
    fix_time: datetime | None
    symbol: str | None
    category: int | None
    time_offset_hours: float | None
    lon: float
    lat: float


class BulletinAreaSummary(BaseModel):
    """An area without its geometry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    area_type: str | None
    extent: str | None
    wind_type: str | None
    marine_type: str | None
    fix_type: str | None
    fix_time: datetime | None
    polygon_count: int
    ring_count: int
    vertex_count: int
    bbox: BBox | None = None


class BulletinAreaGeometry(BulletinAreaSummary):
    geometry: dict[str, Any] | None = None


class BulletinDetail(BulletinSummary):
    """One bulletin without area geometry."""

    tracks: list[BulletinTrackRead] = []
    fixes: list[BulletinFixRead] = []
    areas: list[BulletinAreaSummary] = []


class BulletinDetailGeometry(BulletinDetail):
    """One bulletin *with* area geometry.

    A separate class rather than an optional field on BulletinDetail: a
    ``response_model`` of the summary type would silently coerce the geometry
    subclass back down and drop the polygons, which is exactly the bug this
    split prevents.
    """

    areas: list[BulletinAreaGeometry] = []


class FeatureCollection(BaseModel):
    """A GeoJSON FeatureCollection, shaped like ``app.gml_to_geojson`` emits."""

    type: str = "FeatureCollection"
    metadata: dict[str, Any] = {}
    bbox: list[float] | None = None
    features: list[dict[str, Any]] = []
