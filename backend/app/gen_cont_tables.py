from pathlib import Path
import pandas as pd
import json
from shapely.geometry import LineString
import geopandas as gpd
from pyproj import Transformer

GEOJSON_DIR = Path("backend/data/geojson")
BEST_TRACK_CSV = Path("backend/data/best_track.csv")
TOWNS_XLSX = Path("backend/data/towns.xlsx")   # NOTE FINALISE THIS PATH
BEST_TRACK_SKIPROWS = 4  # 3 copyright lines + 1 blank before the header

# Columns that interpolate normally (continuous quantities)
LINEAR_COLS = ["LAT", "LON", "MAX_WIND_SPD", "POSITION_UNCERTAINTY", "CENTRAL_PRES"]
# GF = galeforce
# HF = hurricane force
# SF = Storm force

RADIUS_COLS = [
    "MN_RADIUS_GF_WIND", "MN_RADIUS_GF_SECNE", "MN_RADIUS_GF_SECSE", "MN_RADIUS_GF_SECSW", "MN_RADIUS_GF_SECNW",
    "MN_RADIUS_SF_WIND", "MN_RADIUS_SF_SECNE", "MN_RADIUS_SF_SECSE", "MN_RADIUS_SF_SECSW", "MN_RADIUS_SF_SECNW",
    "MN_RADIUS_HF_WIND", "MN_RADIUS_HF_SECNE", "MN_RADIUS_HF_SECSE", "MN_RADIUS_HF_SECSW", "MN_RADIUS_HF_SECNW",
]
_geojson_index_cache: dict | None = None
_best_track_cache: pd.DataFrame | None = None #TODO make some way to udate this cache when new dataset is added

#NOTE pd.DataFrame A collection of labelled columns, where each column is essentially an array of values.
def load_full_best_track() -> pd.DataFrame: 
    global _best_track_cache
    if _best_track_cache is None:
        _best_track_cache = pd.read_csv(BEST_TRACK_CSV, skiprows = BEST_TRACK_SKIPROWS, low_memory=False)
    return _best_track_cache

def load_best_track(cyclone_id: str) -> pd.DataFrame:
    df = load_full_best_track()
    df = df[df.DISTURBANCE_ID == cyclone_id].copy()
    df["TM"] = pd.to_datetime(df["TM"])
    for col in LINEAR_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("TM").reset_index(drop = True)

def _nearest_observed_fill(series: pd.Series) -> pd.Series:
    """
    Fill NaNs with the nearest observed (non-null) value in time, rather
    than linearly interpolating -- used for radius columns specifically,
    so a system newly crossing an intensity threshold jumps to the first
    real observation instead of ramping up from an assumed zero.
    """
     
    observed = series.dropna()
    if observed.empty:
        return series
    obs_times = pd.Series(observed.index, index=observed.index)
    forward = obs_times.reindex(series.index, method = "ffill")
    backward = obs_times.reindex(series.index, method = "bfill")
    forward_dist = (series.index.to_series() - forward).abs()
    backward_dist = (backward - series.index.to_series()).abs()
    use_forward = forward_dist <= backward_dist
    forward_vals = observed.reindex(series.index, method="ffill")
    backward_vals = observed.reindex(series.index, method="bfill")
    return forward_vals.where(use_forward, backward_vals)


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
    for col in RADIUS_COLS:
        reindexed[col] = _nearest_observed_fill(pd.to_numeric(reindexed[col], errors="coerce"))

    reindexed = reindexed.reset_index().rename(columns={"index": "TM"})
    return reindexed[reindexed.TM.isin(grid)].reset_index(drop=True)

def load_locations() -> gpd.GeoDataFrame:
    """
    Real BOM towns/cities list. point_x/point_y are in EPSG:3857 (Web
    Mercator, metres) -- NOT lat/lon degrees -- so they're reprojected to
    EPSG:4326 before use, to match the GML polygons' CRS.
    """
    df = pd.read_excel(TOWNS_XLSX)
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(df.point_x.values, df.point_y.values)

    return gpd.GeoDataFrame(
        {"name": df.proper_name, "state": df.state},
        geometry=gpd.points_from_xy(lons, lats),
        crs="EPSG:4283",
    )

def _geojson_index() -> dict:
    """(distId, fcastTime) -> filepath, built once by scanning what gml_to_geojson.py already wrote.
    
    Builds a lookup dict once by scanning data/geojson/ recursively (across
    WA/QLD/NT subfolders), reading just each file's metadata to key it by
    disturbance ID and forecast issue time, without loading full feature data 
    until load_forecast_geojson() actually needs a specific file.\
    
    NOTE that logic in gml_to_geojson.py has to be run prior to this so that there are jeojson files for each cyclone"""
    
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

def get_best_track_geojson(cyclone_id: str) -> dict | None:
    raw = load_best_track(cyclone_id)
    if raw.empty:
        return None

    interpolated_data = interpolate_best_track(raw)
    interpolated_data = interpolated_data.dropna(subset=["LAT", "LON"])

    line = LineString(zip(interpolated_data.LON, interpolated_data.LAT))
    gdf = gpd.GeoDataFrame([{"disturbance_id": cyclone_id}], geometry=[line], crs="EPSG:4283")
    return gdf.__geo_interface__["features"][0]

def load_locations() -> gpd.GeoDataFrame:
    df = pd.read_excel(TOWNS_XLSX)
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(df.point_x.values, df.point_y.values)
    return gpd.GeoDataFrame({"name": df.proper_name, "State": df.state}, geometry=gpd.points_from_xy(lons, lats),crs="EPSG:4283")

def load_forecast_geojson(disturbance_id: str, fcast_time: str) -> dict | None:
    path = _geojson_index().get(disturbance_id,fcast_time)
    return json.loads(path.read_text() if path else None)

def get_reference_times(disturbance_id: str) -> list[str]:
    return sorted(fcast_time for (dist_id, fcast_time) in _geojson_index() if disturbance_id==dist_id and fcast_time)



# TESTING
if __name__ == "__main__":
    raw = load_best_track("AU202526_34U")   # swap for a real disturbance ID from your CSV
    print(len(raw), raw.TM.min(), raw.TM.max())

    interp = interpolate_best_track(raw)
    print(interp[["TM", "LAT", "LON", "MAX_WIND_SPD"]].head(10))

    # confirm a real observation survives interpolation exactly
    real_row = raw[raw.TM == raw.TM.iloc[5]]
    interp_row = interp[interp.TM == raw.TM.iloc[5]]
    print(real_row[["LAT", "LON", "MAX_WIND_SPD"]])
    print(interp_row[["LAT", "LON", "MAX_WIND_SPD"]])

    # confirm nearest-fill on a synthetic case
    test = pd.Series([10, None, None, None, 40], index=pd.date_range("2026-01-01", periods=5, freq="h"))
    print(_nearest_observed_fill(test))

    # confirm the track GeoJSON is valid and roughly the right shape
    geo = get_best_track_geojson("AU202526_34U")
    print(geo["geometry"]["type"], len(geo["geometry"]["coordinates"]), "points")