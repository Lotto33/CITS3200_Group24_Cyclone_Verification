from time import monotonic, sleep

from app.api.v1.endpoints import datasets
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
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("dataset.zip", b"zip contents", "application/zip")},
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
