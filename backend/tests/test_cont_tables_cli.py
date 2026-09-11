import pandas as pd

import backend.app.gen_cont_tables as gen_cont_tables
from backend.app.gen_cont_tables import generate_contingency_dict, generate_table_d


def test_generate_contingency_dict_counts_expected_cells():
    table_d = pd.DataFrame(
        [
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "A", "Forecast": True, "Observed": True},
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "B", "Forecast": True, "Observed": False},
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "C", "Forecast": False, "Observed": True},
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "D", "Forecast": False, "Observed": False},
        ]
    )

    stats = generate_contingency_dict(table_d)

    assert stats["hit"] == 1
    assert stats["false alarm"] == 1
    assert stats["miss"] == 1
    assert stats["correct negative"] == 1
    assert stats["total"] == 4


def test_generate_table_d_merges_forecast_and_observed_columns():
    table_a = pd.DataFrame(
        [
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "A", "Watch": True, "Warning": False},
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "B", "Watch": False, "Warning": False},
        ]
    )
    table_c = pd.DataFrame(
        [
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "A", "Observed": True},
            {"Disturbance ID": "TEST1", "Base time": pd.Timestamp("2024-01-01 00:00:00"), "Location": "B", "Observed": False},
        ]
    )

    table_d = generate_table_d(table_a, table_c)

    assert list(table_d.columns) == ["Disturbance ID", "Base time", "Location", "Forecast", "Observed"]
    assert table_d["Forecast"].tolist() == [True, False]
    assert table_d["Observed"].tolist() == [True, False]


def test_state_filter_is_applied_before_table_a(monkeypatch):
    locations = pd.DataFrame(
        [
            {"name": "WA town", "state": "WA"},
            {"name": "QLD town", "state": "QLD"},
        ]
    )
    locations["geometry"] = None
    captured = {}

    def fake_load_locations():
        return locations

    def fake_generate_table_a(disturbance_id, filtered_locations, **kwargs):
        captured["locations"] = filtered_locations
        return pd.DataFrame(
            columns=[
                "Disturbance ID", "Base time", "Location", "Distance to watch",
                "Distance to warning", "Watch", "Warning",
            ]
        )

    monkeypatch.setattr(gen_cont_tables, "load_locations", fake_load_locations)
    monkeypatch.setattr(gen_cont_tables, "generate_table_a", fake_generate_table_a)
    monkeypatch.setattr(gen_cont_tables, "generate_table_b", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(gen_cont_tables, "generate_table_c", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        gen_cont_tables,
        "generate_table_d",
        lambda *args, **kwargs: pd.DataFrame(
            columns=["Disturbance ID", "Base time", "Location", "Season", "Forecast", "Observed"]
        ),
    )

    result = gen_cont_tables.generate_all_tables_for_disturbance("TEST1", state="WA")

    assert captured["locations"]["name"].tolist() == ["WA town"]
    assert "State" not in result["table_d"].columns
