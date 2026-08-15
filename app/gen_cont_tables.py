from pathlib import Path
import pandas as pd
import geopandas as gpd

BEST_TRACK_CSV = Path("app/data/best_track.csv")
BEST_TRACK_SKIPROWS = 4  # 3 copyright lines + 1 blank before the header

# Columns that interpolate normally (continuous quantities)
LINEAR_COLS = ["LAT", "LON", "MAX_WIND_SPD", "POSITION_UNCERTAINTY", "CENTRAL_PRES"]

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

