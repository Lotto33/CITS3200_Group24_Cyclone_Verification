"""GML bulletin loader.

These run against real bulletins rather than a synthetic fixture: the point of
this loader is that it handles BoM's actual output -- polygons with holes,
antimeridian splits, empty ``<category />`` elements, free-text extents -- and
a fixture I wrote myself would only test my own assumptions.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.disturbance import Disturbance
from app.models.enums import AreaKind, FixType, TrackType
from app.models.gml import Bulletin, BulletinArea, BulletinFix, BulletinTrack
from app.services.loaders.common import Stats
from app.services.loaders.gml import (
    as_multipolygon,
    load_bulletin_file,
    load_bulletins,
    parse_bulletin_features,
    product_id_of,
    region_dirs,
    relative_source,
)

pytestmark = pytest.mark.requires_data

#: A bulletin whose polygons contain an interior ring.
WITH_HOLE = "productfile.20180324.0754.101761021.IDD65409.gml"
#: A bulletin carrying both a watch and a warning area.
WITH_WATCH_AND_WARNING = "productfile.20170218.1658.100402674.IDD65401.gml"


def _find(name: str) -> Path:
    for directory in region_dirs().values():
        for path in directory.rglob(name):
            return path
    pytest.skip(f"{name} is not present")


def test_product_id_is_parsed_from_the_filename():
    assert product_id_of(Path(WITH_HOLE)) == "IDD65409"
    assert product_id_of(Path("not-a-product-file.gml")) is None


def test_source_file_is_relative_and_posix():
    path = _find(WITH_HOLE)
    source = relative_source(path)
    assert source.endswith(WITH_HOLE)
    assert "\\" not in source, "must be portable across Windows and POSIX"
    assert not source.startswith("/")


def test_single_polygons_are_promoted_to_multipolygon():
    square = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    out = as_multipolygon({"type": "Polygon", "coordinates": [square]})
    assert len(out) == 1  # one polygon
    assert len(out[0]) == 1  # one ring
    assert out[0][0][0] == out[0][0][-1], "ring must stay closed"


def test_degenerate_rings_are_dropped():
    assert as_multipolygon({"type": "Polygon", "coordinates": [[[0.0, 0.0]]]}) == []
    assert as_multipolygon({"type": "Point", "coordinates": [0.0, 0.0]}) == []
    assert as_multipolygon(None) == []


def test_coordinates_are_rounded_and_deduplicated():
    """Rounding can make neighbouring vertices identical."""
    ring = [
        [1.000001, 2.000001],
        [1.000002, 2.000002],  # rounds onto the previous point
        [3.0, 4.0],
        [5.0, 6.0],
        [1.000001, 2.000001],
    ]
    out = as_multipolygon({"type": "Polygon", "coordinates": [ring]})
    assert out
    points = out[0][0]
    decimals = [len(f"{c:.10f}".rstrip("0").split(".")[1]) for p in points for c in p]
    assert max(decimals) <= 4
    assert points[0] != points[1]


def test_polygon_with_a_hole_keeps_both_rings(db: Session):
    path = _find(WITH_HOLE)
    outcome = load_bulletin_file(db, "NT", path)
    db.flush()
    assert outcome == "written"

    multi_ring = (
        db.execute(
            select(BulletinArea).where(
                BulletinArea.ring_count > BulletinArea.polygon_count
            )
        )
        .scalars()
        .all()
    )
    assert multi_ring, "this bulletin has an interior ring"
    for area in multi_ring:
        rings = [len(p) for p in area.geometry["coordinates"]]
        assert max(rings) >= 2
        assert area.geometry["type"] == "MultiPolygon"
        assert area.ring_count == sum(rings)


def test_counts_and_bbox_agree_with_the_geometry(db: Session):
    load_bulletin_file(db, "NT", _find(WITH_HOLE))
    db.flush()
    for area in db.execute(select(BulletinArea)).scalars():
        polygons = area.geometry["coordinates"]
        points = [pt for poly in polygons for ring in poly for pt in ring]
        assert area.polygon_count == len(polygons)
        assert area.ring_count == sum(len(p) for p in polygons)
        assert area.vertex_count == len(points)
        assert area.bbox_min_lon == min(p[0] for p in points)
        assert area.bbox_max_lat == max(p[1] for p in points)


def test_watch_and_warning_areas_are_distinguished(db: Session):
    load_bulletin_file(db, "NT", _find(WITH_WATCH_AND_WARNING))
    db.flush()
    kinds = set(db.execute(select(BulletinArea.kind).distinct()).scalars())
    assert AreaKind.WATCH.value in kinds
    assert AreaKind.WARNING.value in kinds

    # An advice area carries area_type/extent and no wind_type; a wind area
    # is the other way round.
    for area in db.execute(
        select(BulletinArea).where(BulletinArea.kind == AreaKind.WATCH.value)
    ).scalars():
        assert area.area_type == "Watch Area"
        assert area.wind_type is None
    for area in db.execute(
        select(BulletinArea).where(BulletinArea.kind == AreaKind.WIND.value)
    ).scalars():
        assert area.area_type is None
        assert area.wind_type is not None


def test_watch_warning_flags_are_derived(db: Session):
    if not any(region_dirs().values()):
        pytest.skip("no GML bulletins present")
    load_bulletins(db, region="NT", limit=40)
    flagged = db.execute(
        select(func.count())
        .select_from(Disturbance)
        .where(Disturbance.has_watch | Disturbance.has_warning)
    ).scalar_one()
    assert flagged >= 1


def test_empty_category_is_null_never_zero(db: Session):
    """The GML writes <category /> when not applicable."""
    load_bulletin_file(db, "NT", _find(WITH_WATCH_AND_WARNING))
    db.flush()
    assert (
        db.execute(
            select(func.count())
            .select_from(BulletinFix)
            .where(BulletinFix.category == 0)
        ).scalar_one()
        == 0
    )
    categories = {
        c for c in db.execute(select(BulletinFix.category).distinct()).scalars()
    }
    assert categories - {None} <= {1, 2, 3, 4, 5}


def test_time_offset_is_signed(db: Session):
    if not any(region_dirs().values()):
        pytest.skip("no GML bulletins present")
    load_bulletins(db, region="NT", limit=40)
    minimum = db.execute(select(func.min(BulletinFix.time_offset_hours))).scalar()
    assert minimum is not None and minimum < 0


def test_unchanged_file_is_skipped_on_reingest(db: Session):
    path = _find(WITH_HOLE)
    assert load_bulletin_file(db, "NT", path) == "written"
    db.flush()
    assert load_bulletin_file(db, "NT", path) == "skipped"
    db.flush()
    assert load_bulletin_file(db, "NT", path, force=True) == "written"


def test_reingest_does_not_duplicate_children(db: Session):
    path = _find(WITH_HOLE)
    load_bulletin_file(db, "NT", path)
    db.flush()
    before = {
        model.__tablename__: db.execute(
            select(func.count()).select_from(model)
        ).scalar_one()
        for model in (BulletinTrack, BulletinFix, BulletinArea)
    }

    load_bulletin_file(db, "NT", path, force=True)
    db.flush()
    after = {
        model.__tablename__: db.execute(
            select(func.count()).select_from(model)
        ).scalar_one()
        for model in (BulletinTrack, BulletinFix, BulletinArea)
    }
    assert before == after


def test_bulletin_records_gda94_not_wgs84(db: Session):
    load_bulletin_file(db, "NT", _find(WITH_HOLE))
    db.flush()
    bulletin = db.execute(select(Bulletin)).scalars().first()
    assert bulletin.srs == "EPSG:4283"


def test_known_corpus_produces_no_unexpected_enum_values(db: Session):
    """New BoM vocabulary should show up as a diff here, not as a crash."""
    stats = Stats()
    load_bulletins(db, region="NT", limit=120, stats=stats)
    assert not {k: dict(v) for k, v in stats.unknown_enum.items() if v}


def test_track_and_fix_types_are_the_documented_vocabulary(db: Session):
    load_bulletins(db, region="NT", limit=60)
    tracks = {
        t
        for t in db.execute(select(BulletinTrack.track_type).distinct()).scalars()
        if t
    }
    fixes = {
        f for f in db.execute(select(BulletinFix.fix_type).distinct()).scalars() if f
    }
    assert tracks <= {t.value for t in TrackType}
    assert fixes <= {f.value for f in FixType}


def test_parse_returns_metadata_and_grouped_features():
    parsed = parse_bulletin_features(_find(WITH_WATCH_AND_WARNING))
    assert parsed["metadata"]["distId"]
    # tcTrack and tcFix are in every bulletin; areas are optional.
    assert parsed["tracks"]
    assert parsed["fixes"]
