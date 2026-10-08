from pathlib import Path

from app.services import dataset_service


class FakeResponse:
    headers = {"Content-Length": "12"}

    def __init__(self):
        self.data = b"best-track,1"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int) -> bytes:
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


def test_refresh_downloads_from_bom_validates_and_ingests(tmp_path, monkeypatch):
    request_info = {}
    processed = {}

    def fake_urlopen(request, timeout, context):
        request_info["url"] = request.full_url
        request_info["timeout"] = timeout
        request_info["context"] = context
        return FakeResponse()

    def fake_process(csv_path: Path, data_dir: Path):
        processed["bytes"] = csv_path.read_bytes()
        processed["data_dir"] = data_dir
        return {"status": "success", "rows_written": 1}

    monkeypatch.setattr(dataset_service.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dataset_service, "read_best_track_csv", lambda path: object())
    monkeypatch.setattr(dataset_service, "process_uploaded_best_track", fake_process)

    result = dataset_service.refresh_best_track_from_bom(tmp_path)

    assert request_info["url"] == dataset_service.BOM_BEST_TRACK_URL
    assert request_info["timeout"] == 60
    assert request_info["context"].verify_mode == 2
    assert processed["bytes"] == b"best-track,1"
    assert processed["data_dir"] == tmp_path.resolve()
    assert result["source_url"] == dataset_service.BOM_BEST_TRACK_URL
    assert not list((tmp_path / "uploads").glob("bom-best-track-*.csv"))
