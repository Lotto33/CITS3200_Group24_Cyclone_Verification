"""Liveness probe.

The `/api/v1/example/ping` stub that used to be tested here went away with
`app/api/v1/endpoints/example.py`; its own docstring said to delete it once
real routes existed. `tests/test_api.py::test_ping_stub_is_gone` asserts it
stays gone.
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main as main
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_viewer_is_served():
    response = client.get("/visualize.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "BOM Cyclone GML Visualizer" in response.text


def test_homepage_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Cyclone verification workspace" in response.text


def test_initialize_reports_readiness_without_writing(client, engine, monkeypatch):
    monkeypatch.setattr(main, "engine", engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('test')")
        )

    try:
        response = client.get("/initialize")
        post_response = client.post("/initialize")
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE alembic_version"))

    assert response.status_code == 200
    assert post_response.status_code == 405
    assert response.json() == {
        "status": "ready",
        "revision": "test",
        "row_counts": {
            "disturbance": 0,
            "best_track_observation": 0,
            "bulletin": 0,
            "town": 0,
            "interpolation_run": 0,
            "verification_run": 0,
        },
        "message": "Database is ready.",
    }
