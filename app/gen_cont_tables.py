from pathlib import Path
import pandas as pd
import geopandas as gpd
import json

GEOJSON_DIR = Path("data/geojson")
BEST_TRACK_CSV = Path("app/data/best_track.csv")
BEST_TRACK_SKIPROWS = 4  # 3 copyright lines + 1 blank before the header

# Columns that interpolate normally (continuous quantities)
LINEAR_COLS = ["LAT", "LON", "MAX_WIND_SPD", "POSITION_UNCERTAINTY", "CENTRAL_PRES"]
_geojson_index_cache: dict | None = None
_best_track_cache: pd.DataFrame | None = None #TODO make some way to udate this cache when new dataset is added

#NOTE pd.DataFrame A collection of labelled columns, where each column is essentially an array of values.
def load_full_best_track() -> pd.DataFrame: 
    global _best_track_cache
    if _best_track_cache == None:
        _best_track_cache = pd.read_csv(BEST_TRACK_CSV, skiprows = BEST_TRACK_SKIPROWS, low_memory=False)
    return _best_track_cache

def load_best_track(cyclone_id: str) -> pd.DataFrame:
    df = load_full_best_track()
    df = df[df.DISTURBANCE_ID == cyclone_id].copy()
    df["TM"] = pd.to_datetime(df["TM"])
    for col in LINEAR_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("TM").reset_index(drop = True)

def interpolate_best_track(df: pd.DataFrame, step_minutes: int = 15) -> pd.DataFrame:
    # NOTE THIS FUNCTION IS TEMPORARY. USE SIYUS VIA IMPORT -> TODO
    indexed = df.set_index("TM")

    # Build a regular grid, merged with the original observation timestamps
    # so you don't lose the real observed points.
    grid = pd.date_range(indexed.index.min(), indexed.index.max(), freq=f"{step_minutes}min")
    full_index = indexed.index.union(grid).sort_values()
    reindexed = indexed.reindex(full_index)

    for col in LINEAR_COLS:
        reindexed[col] = pd.to_numeric(reindexed[col], errors="coerce").interpolate(method="time")

    reindexed = reindexed.reset_index().rename(columns={"index": "TM"})
    return reindexed[reindexed.TM.isin(grid)].reset_index(drop=True)


def _geojson_index() -> dict:
    """(distId, fcastTime) -> filepath, built once by scanning what gml_to_geojson.py already wrote."""
    """NOTE that logic in gml_to_geojson.py has to be run prior to this so that there are jeojson files for each cyclone"""
    global _geojson_index_cache
    if _geojson_index_cache is None:
        _geojson_index_cache = {}
        for path in GEOJSON_DIR.rglob("*.geojson"):
            meta = json.loads(path.read_text()).get("metadata", {})
            key = (meta.get("distId"), meta.get("fcastTime"))
            _geojson_index_cache[key] = path
    return _geojson_index_cache


def load_forecast_geojson(disturbance_id: str, fcast_time: str) -> dict | None:
    path = _geojson_index().get((disturbance_id, fcast_time))
    return json.loads(path.read_text()) if path else None

# TESTING
# raw = load_best_track("AU202526_34U")
# print(len(raw), raw.TM.min(), raw.TM.max())
# interp = interpolate_best_track(raw)
# print(interp[["TM", "LAT", "LON", "MAX_WIND_SPD"]].head(10))
# # pick a timestamp you know is a real observation, not an interpolated one
# real_row = raw[raw.TM == raw.TM.iloc[5]]
# interp_row = interp[interp.TM == raw.TM.iloc[5]]
# print(real_row[["LAT","LON","MAX_WIND_SPD"]])
# print(interp_row[["LAT","LON","MAX_WIND_SPD"]])
# changed = raw[raw.MAX_WIND_SPD.diff() != 0]
# print(changed[["TM", "MAX_WIND_SPD"]].head())