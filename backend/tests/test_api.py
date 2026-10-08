"""API behaviour, built on a small hand-made dataset.

The geometry assertions are the important ones: a list response that quietly
started carrying polygons would turn a 19 KB reply into megabytes, and nothing
else in the suite would notice.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.best_track import BestTrackObservation
from app.models.disturbance import Disturbance
from app.models.enums import AreaKind, TrackDataset
from app.models.gml import Bulletin, BulletinArea, BulletinFix, BulletinTrack
from app.models.town import Town, TownGroupMembership

SQUARE = [
    [130.0, -12.0],
    [131.0, -12.0],
    [131.0, -11.0],
    [130.0, -11.0],
    [130.0, -12.0],
]


@pytest.fixture
def dataset(seeded_db: Session) -> Session:
    """Two real-looking disturbances plus one BoM test product."""
    real = Disturbance(
        disturbance_id="AU201617_19U",
        name="Alfred",
        region="NT",
        season="2016-17",
        type_code="T",
        has_watch=True,
        has_warning=True,
        has_best_track=True,
    )
    other = Disturbance(
        disturbance_id="AU201718_04U",
        name="Marcus",
        region="WA",
        season="2017-18",
        type_code="T",
        has_best_track=True,
    )
    test_product = Disturbance(
        disturbance_id="AU201617_99U",
        name="TEST-NT-2016",
        region="NT",
        season="2016-17",
        is_test=True,
    )
    seeded_db.add_all([real, other, test_product])
    seeded_db.flush()

    seeded_db.add(
        BestTrackObservation(
            dataset=TrackDataset.BOM_BEST_TRACK.value,
            disturbance_pk=real.id,
            tm=datetime(2017, 2, 17, 0, 0, tzinfo=UTC),
            lat=-16.8,
            lon=138.5,
            central_pres=996,
            max_wind_spd=23.2,
            cyc_type=30,
            pres_wind_relation_used=40,  # not in the 2011 spec
            mn_radius_gf_secne=0,  # known absence
        )
    )
    bulletin = Bulletin(
        disturbance_pk=real.id,
        region="NT",
        source_file="NT_GMLs/unit-test.gml",
        product_id="IDD65401",
        dist_name_raw="Alfred",
        fcast_time=datetime(2017, 2, 17, 0, 0, tzinfo=UTC),
        issue_time=datetime(2017, 2, 17, 1, 25, tzinfo=UTC),
        expiry_hrs=7.0,
        bbox_min_lon=130.0,
        bbox_min_lat=-12.0,
        bbox_max_lon=131.0,
        bbox_max_lat=-11.0,
    )
    seeded_db.add(bulletin)
    seeded_db.flush()
    seeded_db.add_all(
        [
            BulletinTrack(
                bulletin_id=bulletin.id,
                track_type="Observed",
                geometry={"type": "LineString", "coordinates": SQUARE[:3]},
                vertex_count=3,
            ),
            BulletinFix(
                bulletin_id=bulletin.id,
                fix_type="Current",
                symbol="Cyclone",
                category=None,
                time_offset_hours=-12.0,
                lon=130.5,
                lat=-11.5,
            ),
            BulletinArea(
                bulletin_id=bulletin.id,
                kind=AreaKind.WATCH.value,
                area_type="Watch Area",
                extent="Port McArthur to NT/Qld Border",
                geometry={"type": "MultiPolygon", "coordinates": [[SQUARE]]},
                polygon_count=1,
                ring_count=1,
                vertex_count=len(SQUARE),
                bbox_min_lon=130.0,
                bbox_min_lat=-12.0,
                bbox_max_lon=131.0,
                bbox_max_lat=-11.0,
            ),
        ]
    )
    town = Town(name="Darwin", state="NT", lat=-12.4, lon=130.87, is_major=True)
    seeded_db.add(town)
    seeded_db.flush()
    seeded_db.add(
        TownGroupMembership(town_id=town.id, town_group="nt_towns", coastal_order=57.0)
    )
    seeded_db.flush()
    return seeded_db


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_excludes_test_products_by_default(client: TestClient, dataset):
    body = client.get("/api/v1/disturbances").json()
    ids = [item["disturbance_id"] for item in body["items"]]
    assert "AU201617_99U" not in ids
    assert body["total"] == 2


def test_include_test_shows_them(client: TestClient, dataset):
    body = client.get("/api/v1/disturbances?include_test=true").json()
    assert body["total"] == 3


def test_filters(client: TestClient, dataset):
    assert client.get("/api/v1/disturbances?season=2017-18").json()["total"] == 1
    assert client.get("/api/v1/disturbances?region=NT").json()["total"] == 1
    assert (
        client.get("/api/v1/disturbances?has_watch_or_warning=true").json()["total"]
        == 1
    )


def test_pagination_envelope(client: TestClient, dataset):
    body = client.get("/api/v1/disturbances?limit=1&offset=1").json()
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["total"] == 2
    assert len(body["items"]) == 1


def test_limit_is_capped(client: TestClient, dataset):
    assert client.get("/api/v1/disturbances?limit=100000").status_code == 422


def test_detail_resolves_the_type_label(client: TestClient, dataset):
    body = client.get("/api/v1/disturbances/AU201617_19U").json()
    assert body["name"] == "Alfred"
    assert body["type_description"] == "Tropical cyclone"
    assert body["datasets"] == ["bom_best_track"]


def test_missing_disturbance_is_404(client: TestClient, dataset):
    assert client.get("/api/v1/disturbances/NOPE").status_code == 404


def test_best_track_returns_the_plottable_subset(client: TestClient, dataset):
    body = client.get("/api/v1/disturbances/AU201617_19U/best-track").json()
    assert len(body) == 1
    point = body[0]
    assert point["central_pres"] == 996
    assert point["mn_radius_gf_wind"] is None
    # The subset must stay a subset: the full 79 fields are elsewhere.
    assert "comment_text" not in point
    assert "max_rep_tide_anom" not in point


def test_full_observation_carries_every_field_and_code_labels(
    client: TestClient, dataset
):
    body = client.get(
        "/api/v1/disturbances/AU201617_19U/observations/2017-02-17T00:00:00Z"
    ).json()
    assert body["comment_text"] is None
    assert body["mn_radius_gf_secne"] == 0, "explicit zero must survive to the API"
    assert body["code_labels"]["cyc_type"].startswith("34-63 knots")
    # Code 40 is real data the spec omits, so no label exists for it but the
    # value is still served.
    assert body["pres_wind_relation_used"] == 40
    assert "pres_wind_relation_used" not in body["code_labels"]


def test_bulletin_list_carries_no_geometry(client: TestClient, dataset):
    response = client.get("/api/v1/disturbances/AU201617_19U/bulletins")
    assert response.status_code == 200
    assert "geometry" not in response.text
    body = response.json()
    assert body[0]["area_count"] == 1
    assert body[0]["vertex_count"] == len(SQUARE)
    assert body[0]["bbox"]["min_lon"] == 130.0


def test_bulletin_detail_omits_area_geometry_by_default(client: TestClient, dataset):
    bulletin_id = client.get("/api/v1/disturbances/AU201617_19U/bulletins").json()[0][
        "id"
    ]
    body = client.get(f"/api/v1/bulletins/{bulletin_id}").json()
    assert body["areas"][0].get("geometry") is None
    assert "geometry" not in body["areas"][0]
    # Tracks are small, so they always carry theirs.
    assert body["tracks"][0]["geometry"]["type"] == "LineString"


def test_bulletin_detail_includes_geometry_on_request(client: TestClient, dataset):
    bulletin_id = client.get("/api/v1/disturbances/AU201617_19U/bulletins").json()[0][
        "id"
    ]
    body = client.get(f"/api/v1/bulletins/{bulletin_id}?include=geometry").json()
    geometry = body["areas"][0]["geometry"]
    assert geometry["type"] == "MultiPolygon"
    assert geometry["coordinates"][0][0] == SQUARE


def test_vertex_budget_returns_413(client: TestClient, dataset, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_RESPONSE_VERTICES", 1)
    bulletin_id = client.get("/api/v1/disturbances/AU201617_19U/bulletins").json()[0][
        "id"
    ]
    geometry = client.get(f"/api/v1/bulletins/{bulletin_id}?include=geometry")
    assert geometry.status_code == 413
    assert client.get(f"/api/v1/bulletins/{bulletin_id}/geojson").status_code == 413
    # The summary route is unaffected: it reads no geometry.
    assert client.get(f"/api/v1/bulletins/{bulletin_id}").status_code == 200


def test_geojson_matches_the_viewer_shape(client: TestClient, dataset):
    bulletin_id = client.get("/api/v1/disturbances/AU201617_19U/bulletins").json()[0][
        "id"
    ]
    body = client.get(f"/api/v1/bulletins/{bulletin_id}/geojson").json()
    assert body["type"] == "FeatureCollection"
    assert body["metadata"]["distId"] == "AU201617_19U"
    assert body["metadata"]["srs"] == "EPSG:4283"
    assert body["bbox"] == [130.0, -12.0, 131.0, -11.0]
    types = {f["properties"]["featureType"] for f in body["features"]}
    assert types == {"tcFix", "tcTrack", "tcWatchArea"}
    for feature in body["features"]:
        assert feature["geometry"], "every feature needs geometry here"
        assert feature["properties"]["distId"] == "AU201617_19U"


def test_towns(client: TestClient, dataset):
    body = client.get("/api/v1/towns").json()
    assert len(body) == 1
    assert body[0]["groups"] == [{"town_group": "nt_towns", "coastal_order": 57.0}]
    assert client.get("/api/v1/towns?state=WA").json() == []
    assert client.get("/api/v1/towns/groups").json() == {"nt_towns": 1}


def test_codes(client: TestClient, dataset):
    body = client.get("/api/v1/codes/cyc_type").json()
    codes = {v["code"]: v["description"] for v in body["values"]}
    assert codes["40"] == "Greater than 63 knots (> 32 m/s)"
    assert client.get("/api/v1/codes/nonsense").status_code == 404
    assert len(client.get("/api/v1/codes").json()) == 13


def test_no_verification_run_is_404_with_a_useful_message(client: TestClient, dataset):
    """An empty database should say how to populate it."""
    response = client.get("/api/v1/verification-runs/1/summary")
    assert response.status_code == 404
    assert "app.cli" in response.json()["detail"]
    assert client.get("/api/v1/verification-runs").json() == []


def test_ping_stub_is_gone(client: TestClient):
    assert client.get("/api/v1/example/ping").status_code == 404


def test_openapi_builds(client: TestClient):
    """A broken response_model annotation would only show up here."""
    schema = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/disturbances" in schema["paths"]
    assert "/api/v1/bulletins/{bulletin_id}" in schema["paths"]


def test_interpolated_track_serves_every_wind_radius(
    client: TestClient, dataset: Session
):
    """The map builds gale/storm/hurricane polygons from these fields."""
    from app.models.interpolation import InterpolatedPoint, InterpolationRun

    disturbance = dataset.query(Disturbance).filter_by(disturbance_id="AU201617_19U").one()
    tm = datetime(2017, 1, 1, tzinfo=UTC)
    run = InterpolationRun(created_at=tm, step_minutes=15)
    dataset.add(run)
    dataset.flush()
    dataset.add(
        InterpolatedPoint(
            run_id=run.id,
            disturbance_pk=disturbance.id,
            tm=tm,
            is_interpolated=True,
            lat=-12.0,
            lon=130.0,
            mn_radius_gf_secne=74.0,
            mn_radius_sf_secse=40.0,
            mn_radius_hf_wind=20.0,
        )
    )
    dataset.flush()

    response = client.get("/api/v1/disturbances/AU201617_19U/interpolated-track")

    assert response.status_code == 200
    point = response.json()[0]
    assert point["mn_radius_gf_secne"] == 74.0
    assert point["mn_radius_sf_secse"] == 40.0
    assert point["mn_radius_hf_wind"] == 20.0
    assert point["mn_radius_hf_secnw"] is None
