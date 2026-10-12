from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd
import pytest

from app.gen_cont_tables import filter_base_times
from app.schemas.contigency import ContingencyRequest
from app.services import contigency_service


def test_filter_base_times_uses_utc_hour_and_sorts_timestamps():
    times = [
        "2025-01-01T18:00:00Z",
        "2025-01-01T06:00:00Z",
        "2025-01-01T12:00:00Z",
        "2025-01-01T00:00:00Z",
    ]

    assert filter_base_times(times, [6, 18]) == [
        "2025-01-01T06:00:00Z",
        "2025-01-01T18:00:00Z",
    ]


def test_filter_base_times_without_filter_keeps_all_times():
    times = ["2025-01-01T18:00:00Z", "2025-01-01T00:00:00Z"]
    assert filter_base_times(times, None) == sorted(times)


def test_contingency_request_defaults_to_standard_base_times():
    request = ContingencyRequest(disturbance_ids=["AU202526_34U"])
    assert request.base_time_hours == [0, 6, 12, 18]


def test_contingency_request_rejects_empty_or_unknown_base_times():
    with pytest.raises(ValueError, match="at least one base time"):
        ContingencyRequest(disturbance_ids=["AU202526_34U"], base_time_hours=[])
    with pytest.raises(ValueError, match="Invalid base-time hour"):
        ContingencyRequest(disturbance_ids=["AU202526_34U"], base_time_hours=[3])


@pytest.mark.parametrize(
    ("disturbance_ids", "expected_call"),
    [(["AU202526_34U"], "single"), (["AU202526_34U", "AU202526_35U"], "multiple")],
)
def test_generation_service_forwards_base_time_hours(monkeypatch, tmp_path, disturbance_ids, expected_call):
    captured = {}
    # Minimal database records for the selected disturbances
    disturbances = {
        ident: SimpleNamespace(
            id=i + 1,
            disturbance_id=ident,
            has_best_track=True,
            observation_count=1,
        )
        for i, ident in enumerate(disturbance_ids)
    }

    def single(*args, **kwargs):
        captured.update(kwargs)
        return {
            "stats": {
                "hit": 1,
                "false alarm": 2,
                "miss": 3,
                "correct negative": 4,
                "total": 10,
            }
        }

    def multiple(*args, **kwargs):
        captured.update(kwargs)
        return {
            "combined_stats": {
                "hit": 1,
                "false alarm": 2,
                "miss": 3,
                "correct negative": 4,
                "total": 10,
            }
        }

    monkeypatch.setattr(contigency_service.settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(contigency_service, "generate_all_tables_for_disturbance", single)
    monkeypatch.setattr(contigency_service, "generate_all_tables_for_disturbances", multiple)

    class FakeSession:
        def execute(self, statement):
            return self

        def scalars(self):
            return list(disturbances.values())

    monkeypatch.setattr(
        contigency_service,
        "SessionLocal",
        lambda: nullcontext(FakeSession()),
    )

    monkeypatch.setattr(
        contigency_service,
        "_db_locations",
        lambda session: pd.DataFrame(
            {
                "state": ["WA"],
            }
        ),
    )

    monkeypatch.setattr(
        contigency_service,
        "_db_forecasts",
        lambda session: {disturbance.id: {"2026-03-24T00:00:00Z": {}} for disturbance in disturbances.values()},
    )

    monkeypatch.setattr(
        contigency_service,
        "latest_run_id",
        lambda session, dataset: 1,
    )

    monkeypatch.setattr(
        contigency_service,
        "_db_tracks",
        lambda session, run_id: {
            disturbance.id: pd.DataFrame(
                {
                    "LAT": [-20.0],
                    "LON": [120.0],
                }
            )
            for disturbance in disturbances.values()
        },
    )
    request = ContingencyRequest(
        disturbance_ids=disturbance_ids,
        base_time_hours=[6, 18],
    )

    contigency_service.generate_tables(request)

    assert captured["base_time_hours"] == [6, 18]
    assert "locations" in captured
