from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd

from app.schemas.contigency import ContingencyRequest
from app.services import contigency_service


def test_single_disturbance_uses_database_inputs(monkeypatch, tmp_path):
    disturbance_id = "AU202526_35U"

    disturbance = SimpleNamespace(
        id=1,
        disturbance_id=disturbance_id,
        has_best_track=True,
        observation_count=1,
    )

    locations = pd.DataFrame({"state": ["WA"]})
    forecasts = {"2026-03-24T00:00:00Z": {}}
    track = pd.DataFrame(
        {
            "LAT": [-20.0],
            "LON": [120.0],
        }
    )

    class FakeSession:
        def execute(self, statement):
            return self

        def scalars(self):
            return [disturbance]

    monkeypatch.setattr(
        contigency_service,
        "SessionLocal",
        lambda: nullcontext(FakeSession()),
    )
    monkeypatch.setattr(
        contigency_service,
        "_db_locations",
        lambda session: locations,
    )
    monkeypatch.setattr(
        contigency_service,
        "_db_forecasts",
        lambda session: {1: forecasts},
    )
    monkeypatch.setattr(
        contigency_service,
        "latest_run_id",
        lambda session, dataset: 1,
    )
    monkeypatch.setattr(
        contigency_service,
        "_db_tracks",
        lambda session, run_id: {1: track},
    )
    monkeypatch.setattr(
        contigency_service.settings,
        "DATA_DIR",
        tmp_path,
    )

    captured = {}

    def fake_generator(*args, **kwargs):
        captured.update(kwargs)
        return {
            "stats": {
                "hit": 1,
                "false alarm": 0,
                "miss": 0,
                "correct negative": 1,
                "total": 2,
            },
            "files": [],
        }

    monkeypatch.setattr(
        contigency_service,
        "generate_all_tables_for_disturbance",
        fake_generator,
    )

    request = ContingencyRequest(
        disturbance_ids=[disturbance_id],
    )

    contigency_service.generate_tables(request)

    assert captured["locations"] is locations
    assert captured["forecasts"] is forecasts
    assert captured["track"] is track
