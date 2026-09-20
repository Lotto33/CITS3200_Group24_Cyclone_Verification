from app.main import app


def test_required_api_routes_are_in_openapi():
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/datasets/",
        "/api/v1/datasets/status",
        "/api/v1/datasets/upload",
        "/api/v1/datasets/upload-best-track",
        "/api/v1/datasets/interpolate-best-track",
        "/api/v1/contingency-tables/",
        "/api/v1/contingency-tables/files/{filename}",
        "/api/v1/diagnostics/near-polygon-distances",
        "/api/v1/cyclones/",
        "/api/v1/cyclones/{region}/{dist_id}",
        "/api/v1/cyclones/{dist_id}/best-track",
        "/api/v1/towns",
        "/api/v1/config/map",
    }
    assert expected <= set(paths)
