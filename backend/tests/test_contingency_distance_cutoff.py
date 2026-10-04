import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from app.gen_cont_tables import (
    DISTANCE_UNCERTAINTY_CUTOFF_MULTIPLIER,
    _beyond_observation_cutoff,
    generate_table_b,
)


@pytest.mark.parametrize(
    ("uncertainty", "distances", "expected"),
    [
        (1.0, (101.0, 150.0, 200.0), True),
        (1.0, (100.0, 150.0, 200.0), False),
        (2.0, (201.0, 199.0, 300.0), False),
        (1.0, (101.0, -1.0, 200.0), False),
        (1.0, (101.0, np.nan, 200.0), False),
        (np.nan, (500.0, 600.0, 700.0), False),
    ],
)
def test_beyond_uncertainty_cutoff_is_conservative(uncertainty, distances, expected):
    assert _beyond_observation_cutoff(uncertainty, distances) is expected


def test_table_b_omits_only_provably_unobservable_rows(monkeypatch):
    locations = gpd.GeoDataFrame(
        {"name": ["Example town"]},
        geometry=[Point(0, 0)],
        crs="EPSG:4283",
    )
    track = pd.DataFrame(
        {
            "TM": pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T00:15:00Z"]),
            "LAT": [-20.0, -20.0],
            "LON": [130.0, 130.0],
            "POSITION_UNCERTAINTY": [1.0, 3.0],
            "MN_RADIUS_GF_WIND": [10.0, 10.0],
            "MN_RADIUS_SF_WIND": [20.0, 20.0],
            "MN_RADIUS_HF_WIND": [30.0, 30.0],
        }
    )
    monkeypatch.setattr(
        "app.gen_cont_tables.calculate_geodesic_distance_km", lambda *args: 250.0
    )
    monkeypatch.setattr("app.gen_cont_tables.get_bearing", lambda *args: 0.0)

    result = generate_table_b("TEST", locations, track=track)

    assert DISTANCE_UNCERTAINTY_CUTOFF_MULTIPLIER == 100.0
    assert len(result) == 1
    assert result.iloc[0]["Analysis Uncertainty"] == 3.0
