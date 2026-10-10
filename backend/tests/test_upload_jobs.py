from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep
from zipfile import ZipFile

import pandas as pd

from app.api.v1.endpoints import contingency, datasets
from app.services import upload_jobs


def test_upload_job_streams_printed_messages_and_result():
    def operation():
        print("=== 1. Extract relevant systems ===")
        print("Total GML files: 3448")
        return {"status": "success"}

    job = upload_jobs.start_upload_job("test upload", operation)
    snapshot = wait_for_job(job.job_id)
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert "=== 1. Extract relevant systems ===" in snapshot["messages"]
    assert "Total GML files: 3448" in snapshot["messages"]
    assert snapshot["result"] == {"status": "success"}


def test_upload_job_supports_incremental_message_reads():
    def operation():
        print("first")
        print("second")
        return {}

    job = upload_jobs.start_upload_job("incremental test", operation)
    wait_for_job(job.job_id)
    snapshot = upload_jobs.get_upload_job(job.job_id, since=2)
    assert snapshot is not None
    assert "first" not in snapshot["messages"]
    assert "second" in snapshot["messages"]


def wait_for_job(job_id: str) -> dict:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        snapshot = upload_jobs.get_upload_job(job_id)
        if snapshot and snapshot["status"] in {"completed", "failed"}:
            return snapshot
        sleep(0.01)
    raise AssertionError("Upload job did not finish in time")


def test_upload_route_exposes_backend_messages(client, monkeypatch):
    def fake_process(archive_path, data_dir):
        print("Total GML files: 3448")
        return {"status": "success"}

    monkeypatch.setattr(
        datasets.dataset_service, "process_uploaded_gml_archive", fake_process
    )
    import io

    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("NT_GMLs/example.gml", "<gml />")
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("dataset.zip", archive.getvalue(), "application/zip")},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    deadline = monotonic() + 3
    while monotonic() < deadline:
        job_response = client.get(f"/api/v1/datasets/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()
        if job["status"] in {"completed", "failed"}:
            break
        sleep(0.01)

    assert job["status"] == "completed"
    assert "Total GML files: 3448" in job["messages"]


def test_best_track_upload_route_returns_job(client, monkeypatch):
    monkeypatch.setattr(datasets, "read_best_track_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(
        datasets.dataset_service,
        "process_uploaded_best_track",
        lambda path, data_dir: {"status": "success"},
    )
    response = client.post(
        "/api/v1/datasets/upload-best-track",
        files={"file": ("track.csv", b"valid enough", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["job_id"]


def test_refresh_best_track_route_returns_job(client, monkeypatch):
    monkeypatch.setattr(
        datasets.dataset_service,
        "refresh_best_track_from_bom",
        lambda data_dir: {"status": "success"},
    )
    response = client.post("/api/v1/datasets/refresh-best-track")
    assert response.status_code == 200
    assert response.json()["job_id"]


def test_contingency_generation_runs_as_a_pollable_job(client, monkeypatch):
    expected = {
        "status": "success",
        "disturbance_ids": ["AU202526_34U"],
        "stats": {
            "hit": 1,
            "false_alarm": 2,
            "miss": 3,
            "correct_negative": 4,
            "total": 10,
        },
        "files": {},
    }

    def generate(request):
        print("Generating requested cyclone tables")
        return expected

    monkeypatch.setattr(contingency.contingency_service, "generate_tables", generate)
    response = client.post(
        "/api/v1/contingency-tables/",
        json={"disturbance_ids": ["AU202526_34U"]},
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = wait_for_job(job_id)
    assert job["status"] == "completed"
    assert job["result"] == expected
    assert "Generating requested cyclone tables" in job["messages"]


def test_contingency_generation_rejects_missing_selection(client):
    response = client.post("/api/v1/contingency-tables/", json={})

    assert response.status_code == 400
    assert "disturbance ID or a season" in response.json()["detail"]


def test_failed_job_reports_error_and_removes_temp_file(client, monkeypatch):
    captured: list[Path] = []

    def fail(path, data_dir):
        captured.append(path)
        raise ValueError("pipeline failed")

    monkeypatch.setattr(datasets.dataset_service, "process_uploaded_best_track", fail)
    monkeypatch.setattr(datasets, "read_best_track_csv", lambda path: pd.DataFrame())
    response = client.post(
        "/api/v1/datasets/upload-best-track",
        files={"file": ("track.csv", b"valid enough", "text/csv")},
    )
    job = wait_for_job(response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"] == "pipeline failed"
    assert captured and not captured[0].exists()


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass


def test_gml_upload_processing_calls_database_loader(tmp_path, monkeypatch):
    from app.services import dataset_service

    archive = tmp_path / "gml.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("NT_GMLs/example.gml", "<gml />")
    calls = {}

    monkeypatch.setattr(
        dataset_service,
        "process_gml_dataset",
        lambda input_dir, data_dir: {"status": "static"},
    )
    monkeypatch.setattr(dataset_service, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        dataset_service,
        "load_bulletins",
        lambda session, **kwargs: calls.update(kwargs)
        or {
            "rows_read": 1,
            "rows_written": 1,
            "rows_skipped": 0,
            "no_key": 0,
        },
    )
    monkeypatch.setattr(dataset_service, "ingest_run", fake_ingest_run)
    result = dataset_service.process_uploaded_gml_archive(archive, tmp_path / "data")
    assert result["database_gml_rows_written"] == 1
    assert calls["data_dir"].name == "NT_GMLs"


def test_best_track_processing_calls_database_loaders(tmp_path, monkeypatch):
    from app.services import dataset_service

    source = tmp_path / "track.csv"
    source.write_bytes(b"track")
    calls = []
    monkeypatch.setattr(
        dataset_service,
        "read_best_track_csv",
        lambda path: pd.DataFrame({"id": [1]}),
    )
    monkeypatch.setattr(dataset_service, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        dataset_service,
        "load_best_track",
        lambda *args, **kwargs: calls.append("best")
        or {"rows_read": 1, "rows_written": 1},
    )
    monkeypatch.setattr(
        dataset_service,
        "load_interpolation",
        lambda *args, **kwargs: calls.append("interpolation")
        or {"rows_read": 1, "rows_written": 2},
    )
    monkeypatch.setattr(dataset_service, "ingest_run", fake_ingest_run)
    result = dataset_service.process_uploaded_best_track(source, tmp_path / "data")
    assert calls == ["best", "interpolation"]
    assert result["interpolation"]["rows_written"] == 2


@contextmanager
def fake_ingest_run(session, kind, **kwargs):
    class Run:
        id = 1
        rows_read = 0
        rows_written = 0
        rows_skipped = 0
        stats = {}

    yield Run()
