"""One bulletin, with geometry strictly opt-in.

The vertex budget below is the reason ``bulletin_area.vertex_count`` is a
stored NOT NULL column: the check is a single cheap aggregate, so an
over-large request is refused *before* any geometry is read.
"""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import undefer

from app.api.deps import DbSession
from app.core.config import settings
from app.models.gml import Bulletin, BulletinArea, BulletinFix, BulletinTrack
from app.schemas.common import BBox
from app.schemas.gml import (
    BulletinAreaGeometry,
    BulletinAreaSummary,
    BulletinDetail,
    BulletinDetailGeometry,
    BulletinFixRead,
    BulletinTrackRead,
    FeatureCollection,
)

router = APIRouter()


def _get_bulletin(db: DbSession, bulletin_id: int) -> Bulletin:
    row = db.get(Bulletin, bulletin_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no bulletin {bulletin_id}")
    return row


def _assert_within_budget(db: DbSession, bulletin_id: int) -> int:
    """Refuse a geometry response that would exceed the configured budget."""
    vertices = (
        db.execute(
            select(func.sum(BulletinArea.vertex_count)).where(
                BulletinArea.bulletin_id == bulletin_id
            )
        ).scalar()
        or 0
    )
    if vertices > settings.MAX_RESPONSE_VERTICES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"bulletin geometry has {vertices} vertices, over the "
                f"{settings.MAX_RESPONSE_VERTICES} budget; request individual "
                "areas instead"
            ),
        )
    return vertices


# response_model is left off deliberately: FastAPI would coerce the returned
# model to the annotated type and strip the geometry from the subclass. The
# union below still documents both shapes in the OpenAPI schema.
@router.get(
    "/{bulletin_id}",
    response_model=None,
    responses={200: {"model": BulletinDetailGeometry}},
)
def get_bulletin(
    db: DbSession,
    bulletin_id: int,
    include: Annotated[
        str | None,
        Query(description="Pass 'geometry' to include area polygons"),
    ] = None,
) -> BulletinDetail | BulletinDetailGeometry:
    """One bulletin. Area geometry only when ``include=geometry``."""
    bulletin = _get_bulletin(db, bulletin_id)
    want_geometry = (include or "").strip().lower() == "geometry"
    if want_geometry:
        _assert_within_budget(db, bulletin_id)

    # Tracks are small enough to always carry their geometry.
    tracks = db.execute(
        select(BulletinTrack)
        .where(BulletinTrack.bulletin_id == bulletin_id)
        .options(undefer(BulletinTrack.geometry))
        .order_by(BulletinTrack.id)
    ).scalars()
    fixes = db.execute(
        select(BulletinFix)
        .where(BulletinFix.bulletin_id == bulletin_id)
        .order_by(BulletinFix.fix_time, BulletinFix.id)
    ).scalars()

    area_query = (
        select(BulletinArea)
        .where(BulletinArea.bulletin_id == bulletin_id)
        .order_by(BulletinArea.kind, BulletinArea.id)
    )
    if want_geometry:
        area_query = area_query.options(undefer(BulletinArea.geometry))

    areas: list[BulletinAreaSummary] = []
    total_vertices = 0
    for row in db.execute(area_query).scalars():
        model = BulletinAreaGeometry if want_geometry else BulletinAreaSummary
        area = model.model_validate(row)
        area.bbox = BBox.from_row(row)
        areas.append(area)
        total_vertices += row.vertex_count

    model = BulletinDetailGeometry if want_geometry else BulletinDetail
    detail = model.model_validate(bulletin)
    detail.disturbance_id = bulletin.disturbance.disturbance_id
    detail.bbox = BBox.from_row(bulletin)
    detail.tracks = [BulletinTrackRead.model_validate(t) for t in tracks]
    detail.fixes = [BulletinFixRead.model_validate(f) for f in fixes]
    detail.areas = areas
    detail.track_count = len(detail.tracks)
    detail.fix_count = len(detail.fixes)
    detail.area_count = len(areas)
    detail.vertex_count = total_vertices
    return detail


@router.get("/{bulletin_id}/geojson", response_model=FeatureCollection)
def get_bulletin_geojson(db: DbSession, bulletin_id: int) -> FeatureCollection:
    """One bulletin as GeoJSON, shaped like ``app.gml_to_geojson`` emits.

    Matches what the Leaflet and OpenLayers viewers already consume, so the
    pages can be repointed from the static files to this route.
    """
    bulletin = _get_bulletin(db, bulletin_id)
    _assert_within_budget(db, bulletin_id)

    base = {
        "source_file": bulletin.source_file,
        "fcastTime": _iso(bulletin.fcast_time),
        "issueTime": _iso(bulletin.issue_time),
        "expiryHrs": bulletin.expiry_hrs,
        "distId": bulletin.disturbance.disturbance_id,
        "distName": bulletin.dist_name_raw,
    }
    features: list[dict[str, Any]] = []

    for fix in db.execute(
        select(BulletinFix)
        .where(BulletinFix.bulletin_id == bulletin_id)
        .order_by(BulletinFix.fix_time, BulletinFix.id)
    ).scalars():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    **base,
                    "featureType": "tcFix",
                    "fixType": fix.fix_type,
                    "fixTime": _iso(fix.fix_time),
                    "symbol": fix.symbol,
                    "category": fix.category,
                    "timeOffset": fix.time_offset_hours,
                },
                "geometry": {"type": "Point", "coordinates": [fix.lon, fix.lat]},
            }
        )

    for track in db.execute(
        select(BulletinTrack)
        .where(BulletinTrack.bulletin_id == bulletin_id)
        .options(undefer(BulletinTrack.geometry))
        .order_by(BulletinTrack.id)
    ).scalars():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    **base,
                    "featureType": "tcTrack",
                    "trackType": track.track_type,
                    "startTime": _iso(track.start_time),
                    "endTime": _iso(track.end_time),
                },
                "geometry": track.geometry,
            }
        )

    for area in db.execute(
        select(BulletinArea)
        .where(BulletinArea.bulletin_id == bulletin_id)
        .options(undefer(BulletinArea.geometry))
        .order_by(BulletinArea.kind, BulletinArea.id)
    ).scalars():
        properties = {**base, "featureType": area.kind}
        if area.kind == "tcWindArea":
            properties.update(
                {
                    "windType": area.wind_type,
                    "marineType": area.marine_type,
                    "fixType": area.fix_type,
                    "fixTime": _iso(area.fix_time),
                }
            )
        else:
            properties.update({"areaType": area.area_type, "extent": area.extent})
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": area.geometry,
            }
        )

    bbox = None
    if bulletin.bbox_min_lon is not None:
        bbox = [
            bulletin.bbox_min_lon,
            bulletin.bbox_min_lat,
            bulletin.bbox_max_lon,
            bulletin.bbox_max_lat,
        ]

    return FeatureCollection(
        metadata={
            "fcastTime": base["fcastTime"],
            "issueTime": base["issueTime"],
            "expiryHrs": bulletin.expiry_hrs,
            "distId": base["distId"],
            "distName": base["distName"],
            "srs": bulletin.srs,
        },
        bbox=bbox,
        features=features,
    )


@router.get("/{bulletin_id}/areas/{area_id}", response_model=BulletinAreaGeometry)
def get_area(db: DbSession, bulletin_id: int, area_id: int) -> BulletinAreaGeometry:
    """One area with its geometry, for when a whole bulletin is too large."""
    row = db.execute(
        select(BulletinArea)
        .where(BulletinArea.id == area_id, BulletinArea.bulletin_id == bulletin_id)
        .options(undefer(BulletinArea.geometry))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"no area {area_id} on bulletin {bulletin_id}"
        )
    area = BulletinAreaGeometry.model_validate(row)
    area.bbox = BBox.from_row(row)
    return area


def _iso(value) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None
