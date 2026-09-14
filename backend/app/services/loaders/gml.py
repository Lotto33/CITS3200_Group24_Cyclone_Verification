"""Load BoM GML bulletins into ``bulletin`` + tracks / fixes / areas.

Geometry parsing is **not** reimplemented here: this calls
:func:`app.gml_to_geojson.build_feature_collection`, the same function
``build_gml_dataset.py`` uses, so the GML-to-GeoJSON logic stays in one place.
That module's docstring states this as a design goal; this honours it.

The corpus is 3,448 files and about 487 MB of XML, so the loader commits per
file and skips a file whose sha256 already matches its ``bulletin`` row.
Coordinates are rounded to four decimal places (roughly 11 m) on the way in:
BoM's polygon vertices are not meaningful below that, and it typically removes
30-40% of the JSON.
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.gml_to_geojson import build_feature_collection
from app.models.disturbance import Disturbance
from app.models.enums import (
    AreaKind,
    AreaType,
    FixSymbol,
    FixType,
    MarineType,
    Region,
    TrackType,
    WindType,
)
from app.models.gml import (
    DEFAULT_SRS,
    Bulletin,
    BulletinArea,
    BulletinFix,
    BulletinTrack,
)
from app.services.loaders.common import (
    Stats,
    clean_cell,
    coerce_enum,
    is_test_disturbance,
    season_of,
    to_datetime,
    to_float,
    to_int,
)

log = logging.getLogger(__name__)

#: ~11 m. Enough for polygons whose vertices BoM publishes to 6 dp but
#: computes from a coarse wind model.
COORD_PRECISION = 4

GML_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

#: productfile.<date>.<time>.<sequence>.<productId>.gml
_PRODUCT_ID_RE = re.compile(r"^productfile\.\d+\.\d+\.\d+\.([A-Z0-9]+)\.gml$")

_AREA_KINDS = {k.value for k in AreaKind}


def region_dirs() -> dict[str, Path]:
    """``{region: directory}`` for the regional GML folders that exist.

    Note the layout is ``data/<REGION>_GMLs/``. The interpolation pipeline's
    ``relevant_system_extraction`` looks in ``data/gml/`` instead, which does
    not exist -- see :func:`iter_gml_files`.
    """
    found = {}
    for region in Region:
        directory = settings.DATA_DIR / f"{region.value}_GMLs"
        if directory.is_dir():
            found[region.value] = directory
    # Tolerate the layout the other scripts expect, if someone creates it.
    nested = settings.DATA_DIR / "gml"
    if nested.is_dir():
        for region in Region:
            directory = nested / f"{region.value}_GMLs"
            if directory.is_dir():
                found.setdefault(region.value, directory)
    return found


def iter_gml_files(region: str | None = None) -> Iterator[tuple[str, Path]]:
    """Yield ``(region, path)`` for every bulletin, sorted for determinism."""
    for name, directory in sorted(region_dirs().items()):
        if region and name != region:
            continue
        for path in sorted(directory.rglob("*.gml")):
            if path.is_file():
                yield name, path


def product_id_of(path: Path) -> str | None:
    match = _PRODUCT_ID_RE.match(path.name)
    return match.group(1) if match else None


def relative_source(path: Path) -> str:
    """Path relative to ``DATA_DIR``, with forward slashes.

    Stored rather than the absolute path so the same database is usable from a
    different checkout, and so it is stable across Windows and POSIX.
    """
    try:
        return path.relative_to(settings.DATA_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _round_point(point: Any) -> list[float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    try:
        return [
            round(float(point[0]), COORD_PRECISION),
            round(float(point[1]), COORD_PRECISION),
        ]
    except (TypeError, ValueError):
        return None


def _round_line(coords: Any) -> list[list[float]]:
    """Round a coordinate list and drop consecutive duplicates.

    Rounding can make neighbouring vertices identical, and the antimeridian
    handling in ``gml_to_geojson`` can emit repeats of its own.
    """
    out: list[list[float]] = []
    for raw in coords or []:
        point = _round_point(raw)
        if point is None:
            continue
        if out and out[-1] == point:
            continue
        out.append(point)
    return out


def _round_ring(ring: Any) -> list[list[float]]:
    """Round a polygon ring, keeping it closed and at least a triangle."""
    out = _round_line(ring)
    if len(out) >= 3 and out[0] != out[-1]:
        out.append(list(out[0]))
    return out if len(out) >= 4 else []


def bbox_of(points: list[list[float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)


def as_multipolygon(geometry: dict[str, Any] | None) -> list[list[list[list[float]]]]:
    """Normalise any polygonal geometry to MultiPolygon coordinates.

    Every area row stores the same shape, so a single Polygon is promoted
    rather than stored differently; holes are simply the rings after the first.
    """
    if not geometry:
        return []
    kind = geometry.get("type")
    raw = geometry.get("coordinates") or []
    if kind == "Polygon":
        polygons = [raw]
    elif kind == "MultiPolygon":
        polygons = list(raw)
    else:
        return []

    out: list[list[list[list[float]]]] = []
    for polygon in polygons:
        rings = [r for r in (_round_ring(ring) for ring in polygon or []) if r]
        if rings:
            out.append(rings)
    return out


def parse_bulletin_features(path: Path) -> dict[str, Any]:
    """Parse one bulletin into metadata plus grouped features.

    The file is handed to ElementTree as a path so the XML declaration decides
    the encoding. At least one bulletin has mojibake in an ``extent``, and
    forcing utf-8 with ``errors='replace'`` would corrupt more than it fixes.
    """
    root = ET.parse(str(path)).getroot()
    collection = build_feature_collection(root)
    metadata = collection.get("metadata") or {}

    tracks: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    areas: list[dict[str, Any]] = []

    for feature in collection.get("features") or []:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        feature_type = properties.get("featureType")

        if feature_type == "tcTrack":
            tracks.append({"properties": properties, "geometry": geometry})
        elif feature_type == "tcFix":
            fixes.append({"properties": properties, "geometry": geometry})
        elif feature_type in _AREA_KINDS:
            areas.append(
                {
                    "kind": feature_type,
                    "properties": properties,
                    "geometry": geometry,
                }
            )

    return {
        "metadata": metadata,
        "bbox": collection.get("bbox"),
        "tracks": tracks,
        "fixes": fixes,
        "areas": areas,
    }


def _track_rows(
    bulletin_id: int, tracks: list[dict[str, Any]], stats: Stats
) -> list[dict[str, Any]]:
    rows = []
    for track in tracks:
        properties = track["properties"]
        coords = _round_line((track["geometry"] or {}).get("coordinates"))
        if len(coords) < 2:
            continue
        box = bbox_of(coords)
        rows.append(
            {
                "bulletin_id": bulletin_id,
                "track_type": coerce_enum(
                    properties.get("trackType"),
                    TrackType,
                    field="track_type",
                    stats=stats,
                ),
                "start_time": to_datetime(
                    properties.get("startTime"), GML_TIME_FORMAT, field="startTime"
                ),
                "end_time": to_datetime(
                    properties.get("endTime"), GML_TIME_FORMAT, field="endTime"
                ),
                "geometry": {"type": "LineString", "coordinates": coords},
                "vertex_count": len(coords),
                "bbox_min_lon": box[0],
                "bbox_min_lat": box[1],
                "bbox_max_lon": box[2],
                "bbox_max_lat": box[3],
            }
        )
    return rows


def _fix_rows(
    bulletin_id: int, fixes: list[dict[str, Any]], stats: Stats
) -> list[dict[str, Any]]:
    rows = []
    for fix in fixes:
        properties = fix["properties"]
        point = _round_point((fix["geometry"] or {}).get("coordinates"))
        if point is None:
            continue
        rows.append(
            {
                "bulletin_id": bulletin_id,
                "fix_type": coerce_enum(
                    properties.get("fixType"), FixType, field="fix_type", stats=stats
                ),
                "fix_time": to_datetime(
                    properties.get("fixTime"), GML_TIME_FORMAT, field="fixTime"
                ),
                "symbol": coerce_enum(
                    properties.get("symbol"), FixSymbol, field="symbol", stats=stats
                ),
                # An empty <category /> must stay NULL, never become 0.
                "category": to_int(properties.get("category"), field="category"),
                "time_offset_hours": to_float(
                    properties.get("timeOffset"), field="timeOffset"
                ),
                "lon": point[0],
                "lat": point[1],
            }
        )
    return rows


def _area_rows(
    bulletin_id: int, areas: list[dict[str, Any]], stats: Stats
) -> list[dict[str, Any]]:
    rows = []
    for area in areas:
        properties = area["properties"]
        polygons = as_multipolygon(area["geometry"])
        if not polygons:
            continue
        points = [pt for polygon in polygons for ring in polygon for pt in ring]
        box = bbox_of(points)
        if box is None:
            continue
        rows.append(
            {
                "bulletin_id": bulletin_id,
                "kind": area["kind"],
                "area_type": coerce_enum(
                    properties.get("areaType"), AreaType, field="area_type", stats=stats
                ),
                "extent": clean_cell(properties.get("extent")),
                "wind_type": coerce_enum(
                    properties.get("windType"), WindType, field="wind_type", stats=stats
                ),
                "marine_type": coerce_enum(
                    properties.get("marineType"),
                    MarineType,
                    field="marine_type",
                    stats=stats,
                ),
                "fix_type": coerce_enum(
                    properties.get("fixType"), FixType, field="fix_type", stats=stats
                ),
                "fix_time": to_datetime(
                    properties.get("fixTime"), GML_TIME_FORMAT, field="fixTime"
                ),
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
                "polygon_count": len(polygons),
                "ring_count": sum(len(p) for p in polygons),
                "vertex_count": len(points),
                "bbox_min_lon": box[0],
                "bbox_min_lat": box[1],
                "bbox_max_lon": box[2],
                "bbox_max_lat": box[3],
            }
        )
    return rows


def load_bulletin_file(
    session: Session,
    region: str,
    path: Path,
    *,
    ingest_run_id: int | None = None,
    force: bool = False,
    stats: Stats | None = None,
) -> str:
    """Ingest one bulletin. Returns 'written', 'skipped' or 'no-key'."""
    stats = stats if stats is not None else Stats()
    source = relative_source(path)
    digest = sha256_of(path)

    bulletin = session.execute(
        select(Bulletin).where(Bulletin.source_file == source)
    ).scalar_one_or_none()
    if bulletin is not None and bulletin.content_hash == digest and not force:
        return "skipped"

    parsed = parse_bulletin_features(path)
    metadata = parsed["metadata"]
    dist_id = clean_cell(metadata.get("distId"))
    if not dist_id:
        stats.conflicts.append(f"{source}: no distId; skipped")
        return "no-key"

    dist_name = clean_cell(metadata.get("distName"))
    disturbance = session.execute(
        select(Disturbance).where(Disturbance.disturbance_id == dist_id)
    ).scalar_one_or_none()
    if disturbance is None:
        # A bulletin can exist for a system with no best track at all: 30 of
        # the 136 bulletin-bearing disturbances have none, either because they
        # are test products or because BoM has not reanalysed that season yet.
        disturbance = Disturbance(
            disturbance_id=dist_id,
            season=season_of(dist_id),
            has_best_track=False,
        )
        session.add(disturbance)
    disturbance.region = disturbance.region or region
    disturbance.name = disturbance.name or dist_name
    disturbance.is_test = disturbance.is_test or is_test_disturbance(
        dist_id, dist_name
    )
    session.flush()

    if bulletin is None:
        bulletin = Bulletin(source_file=source)
        session.add(bulletin)

    # Rounded to match the geometry, which is rounded on the way in.
    raw_box = parsed["bbox"] or [None, None, None, None]
    box = [
        round(v, COORD_PRECISION) if isinstance(v, (int, float)) else None
        for v in raw_box
    ]
    bulletin.disturbance_pk = disturbance.id
    bulletin.region = region
    bulletin.product_id = product_id_of(path)
    bulletin.dist_name_raw = dist_name
    bulletin.fcast_time = to_datetime(
        metadata.get("fcastTime"), GML_TIME_FORMAT, field="fcastTime"
    )
    bulletin.issue_time = to_datetime(
        metadata.get("issueTime"), GML_TIME_FORMAT, field="issueTime"
    )
    bulletin.expiry_hrs = to_float(metadata.get("expiryHrs"), field="expiryHrs")
    bulletin.srs = DEFAULT_SRS
    bulletin.bbox_min_lon, bulletin.bbox_min_lat = box[0], box[1]
    bulletin.bbox_max_lon, bulletin.bbox_max_lat = box[2], box[3]
    bulletin.content_hash = digest
    bulletin.ingest_run_id = ingest_run_id
    session.flush()

    # Children are replaced wholesale. They have no natural key of their own --
    # a bulletin can legitimately carry two areas with identical attributes and
    # different geometry -- so upserting them individually is not possible, and
    # delete-then-insert keeps a re-ingest from accumulating duplicates.
    for model in (BulletinTrack, BulletinFix, BulletinArea):
        session.execute(delete(model).where(model.bulletin_id == bulletin.id))

    for model, rows in (
        (BulletinTrack, _track_rows(bulletin.id, parsed["tracks"], stats)),
        (BulletinFix, _fix_rows(bulletin.id, parsed["fixes"], stats)),
        (BulletinArea, _area_rows(bulletin.id, parsed["areas"], stats)),
    ):
        if rows:
            session.execute(model.__table__.insert(), rows)

    return "written"


def load_bulletins(
    session: Session,
    *,
    region: str | None = None,
    limit: int | None = None,
    force: bool = False,
    ingest_run_id: int | None = None,
    stats: Stats | None = None,
    progress_every: int = 200,
) -> dict[str, int]:
    """Ingest every bulletin, committing per file.

    Per-file commits matter at this scale: a failure 2,000 files into a
    3,448-file pass should not discard the work already parsed.
    """
    stats = stats if stats is not None else Stats()
    counts = {"rows_read": 0, "rows_written": 0, "rows_skipped": 0, "no_key": 0}

    for index, (name, path) in enumerate(iter_gml_files(region), start=1):
        if limit is not None and counts["rows_read"] >= limit:
            break
        counts["rows_read"] += 1
        try:
            outcome = load_bulletin_file(
                session,
                name,
                path,
                ingest_run_id=ingest_run_id,
                force=force,
                stats=stats,
            )
        except ET.ParseError as exc:
            session.rollback()
            stats.conflicts.append(f"{relative_source(path)}: unparseable XML ({exc})")
            counts["no_key"] += 1
            continue

        if outcome == "written":
            counts["rows_written"] += 1
        elif outcome == "skipped":
            counts["rows_skipped"] += 1
        else:
            counts["no_key"] += 1
        session.commit()

        if progress_every and index % progress_every == 0:
            log.info(
                "gml: %d files (%d written, %d skipped)",
                index,
                counts["rows_written"],
                counts["rows_skipped"],
            )

    refresh_bulletin_counts(session)
    refresh_watch_warning_flags(session)
    session.commit()
    stats.notes.update(counts)
    return counts


def refresh_bulletin_counts(session: Session) -> None:
    """Recompute ``disturbance.bulletin_count`` / first and last issue."""
    session.execute(
        Disturbance.__table__.update().values(
            bulletin_count=(
                select(func.count(Bulletin.id))
                .where(Bulletin.disturbance_pk == Disturbance.id)
                .scalar_subquery()
            ),
            first_issue=(
                select(func.min(Bulletin.issue_time))
                .where(Bulletin.disturbance_pk == Disturbance.id)
                .scalar_subquery()
            ),
            last_issue=(
                select(func.max(Bulletin.issue_time))
                .where(Bulletin.disturbance_pk == Disturbance.id)
                .scalar_subquery()
            ),
        )
    )


def refresh_watch_warning_flags(session: Session) -> None:
    """Set ``has_watch`` / ``has_warning`` from the ingested areas.

    This replaces ``data/processed/relevant_disturbance_ids.csv`` as *derived*
    state. The pipeline's own extractor keys off ``areaType`` text; this keys
    off the originating element as well, so a watch area is recognised even if
    its ``areaType`` text is missing.
    """
    for flag, kind, area_type in (
        ("has_watch", AreaKind.WATCH.value, AreaType.WATCH.value),
        ("has_warning", AreaKind.WARNING.value, AreaType.WARNING.value),
    ):
        matching = (
            select(Bulletin.disturbance_pk)
            .join(BulletinArea, BulletinArea.bulletin_id == Bulletin.id)
            .where(
                (BulletinArea.kind == kind) | (BulletinArea.area_type == area_type)
            )
            .distinct()
        )
        session.execute(
            Disturbance.__table__.update()
            .where(Disturbance.id.in_(matching))
            .values(**{flag: True})
        )
