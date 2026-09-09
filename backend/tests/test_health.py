from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_example_ping():
    response = client.get("/api/v1/example/ping")
    assert response.status_code == 200
    assert response.json() == {"ping": "pong"}
