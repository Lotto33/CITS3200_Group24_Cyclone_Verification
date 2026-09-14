"""Liveness probe.

The `/api/v1/example/ping` stub that used to be tested here went away with
`app/api/v1/endpoints/example.py`; its own docstring said to delete it once
real routes existed. `tests/test_api.py::test_ping_stub_is_gone` asserts it
stays gone.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
