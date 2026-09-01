import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union

geod = Geod(ellps="WGS84")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_DIR = PROJECT_ROOT / "data" / "geojson"
BEST_TRACK_CSV = PROJECT_ROOT / "data" / "best_track.csv"
TOWNS_XLSX = PROJECT_ROOT / "data" / "towns.xlsx"   # NOTE FINALISE THIS PATH
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
        print(f"[best_track] Loading {BEST_TRACK_CSV} ...")
        _best_track_cache = pd.read_csv(BEST_TRACK_CSV, skiprows = BEST_TRACK_SKIPROWS, low_memory=False)
        print(f"[best_track] Loaded {len(_best_track_cache)} total rows (all disturbances)")
    return _best_track_cache

def load_best_track(cyclone_id: str) -> pd.DataFrame:
    df = load_full_best_track()
    df = df[df.DISTURBANCE_ID == cyclone_id].copy()
    print(f"[best_track] {len(df)} row(s) matched DISTURBANCE_ID == {cyclone_id!r}")
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
    if df.empty:
        print("[interpolate_best_track] Input best-track slice is empty, nothing to interpolate")
        return df

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
    result = reindexed[reindexed.TM.isin(grid)].reset_index(drop=True)
    print(f"[interpolate_best_track] {len(df)} observed rows -> {len(result)} rows at {step_minutes}min steps")
    return result

def load_locations() -> gpd.GeoDataFrame:
    """
    Real BOM locations list. Latitude/Longitude are plain WGS84 degrees
    already -- no reprojection needed, unlike the earlier GIS towns layer.
    """
    print(f"[locations] Loading {TOWNS_XLSX} (sheet 'TC Locations') ...")
    df = pd.read_excel(TOWNS_XLSX, sheet_name="TC Locations")
    print(f"[locations] Loaded {len(df)} location(s)")
    return gpd.GeoDataFrame(
        {"name": df["Name"], "state": df["State"]},
        geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
        crs="EPSG:4283",
    )
def calculate_geodesic_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates Vincenty/WGS84 distance in kilometers between two points."""
    _, _, distance_m = geod.inv(lon1, lat1, lon2, lat2)
    return distance_m / 1000.0

def get_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the initial compass bearing from point 1 to point 2 in degrees (0 - 360)."""
    initial_bearing, _, _ = geod.inv(lon1, lat1, lon2, lat2)
    return initial_bearing % 360

def get_quadrant_radius(row: pd.Series, prefix: str, bearing: float) -> float:
    """
    Retrieves the wind radius for the specific quadrant matching the bearing.
    Falls back to the mean overall radius if the quadrant value is NaN or 0.
    """
    if 0 <= bearing < 90:
        sec_col = f"{prefix}_SECNE"
    elif 90 <= bearing < 180:
        sec_col = f"{prefix}_SECSE"
    elif 180 <= bearing < 270:
        sec_col = f"{prefix}_SECSW"
    else:
        sec_col = f"{prefix}_SECNW"

    # Try quadrant specific radius first
    val = row.get(sec_col)
    if pd.notna(val) and val > 0:
        return float(val)
    # Fall back to mean radius (e.g., MN_RADIUS_GF_WIND)
    mean_val = row.get(f"{prefix}_WIND")
    if pd.notna(mean_val) and mean_val > 0:
        return float(mean_val)
    return 0.0

def _geojson_index() -> dict:
    """(distId, fcastTime) -> filepath, built once by scanning what gml_to_geojson.py already wrote.
    
    Builds a lookup dict once by scanning data/geojson/ recursively (across
    WA/QLD/NT subfolders), reading just each file's metadata to key it by
    Disturbance ID and forecast issue time, without loading full feature data 
    until load_forecast_geojson() actually needs a specific file.\
    
    NOTE that logic in gml_to_geojson.py has to be run prior to this so that there are jeojson files for each cyclone"""
    
    global _geojson_index_cache
    if _geojson_index_cache is None:
        print(f"[geojson_index] Scanning {GEOJSON_DIR} for *.geojson files ...")
        _geojson_index_cache = {}
        scanned = 0
        for path in GEOJSON_DIR.rglob("*.geojson"):
            scanned += 1
            meta = json.loads(path.read_text()).get("metadata", {})
            key = (meta.get("distId"), meta.get("fcastTime"))
            _geojson_index_cache[key] = path
        print(f"[geojson_index] Found {scanned} file(s), indexed {len(_geojson_index_cache)} unique (distId, fcastTime) key(s)")
        if scanned == 0:
            print(f"[geojson_index] WARNING: no .geojson files found under {GEOJSON_DIR} -- did you run build_gml_dataset.py?")
    return _geojson_index_cache

def load_forecast_geojson(disturbance_id: str, fcast_time: str) -> dict | None:
    path = _geojson_index().get((disturbance_id, fcast_time))
    if path is None:
        print(f"[load_forecast_geojson] No file indexed for ({disturbance_id!r}, {fcast_time!r})")
        return None
    return json.loads(path.read_text())

def get_best_track_geojson(cyclone_id: str) -> dict | None:
    raw = load_best_track(cyclone_id)
    if raw.empty:
        print(f"[get_best_track_geojson] No best-track rows for {cyclone_id!r}, returning None")
        return None

    interpolated_data = interpolate_best_track(raw)
    interpolated_data = interpolated_data.dropna(subset=["LAT", "LON"])

    line = LineString(zip(interpolated_data.LON, interpolated_data.LAT))
    gdf = gpd.GeoDataFrame([{"disturbance_id": cyclone_id}], geometry=[line], crs="EPSG:4283")
    return gdf.__geo_interface__["features"][0]

def get_reference_times(disturbance_id: str) -> list[str]:
    times = sorted(fcast_time for (dist_id, fcast_time) in _geojson_index() if disturbance_id==dist_id and fcast_time)
    print(f"[get_reference_times] {len(times)} forecast base time(s) found for {disturbance_id!r}")
    return times

"""See the client's scope and deliverables"""

def generate_table_a(disturbance_id: str, locations: gpd.GeoDataFrame | None) -> pd.DataFrame:
    """
    create a table from the forecast polygons for each forecast base time including relevant locations
    """
    print(f"\n=== Table A: forecast watch/warning areas for {disturbance_id} ===")
    if locations is None:
        locations = load_locations()
    rows = []
    fcast_times = get_reference_times(disturbance_id)
    for i, fcast_time in enumerate(fcast_times, start=1):
        print(f"[table_a] ({i}/{len(fcast_times)}) base time {fcast_time}")
        geo = load_forecast_geojson(disturbance_id,fcast_time)
        if geo is None:
            print(f"[table_a]   -> no geojson found, skipping this base time")
            continue

        watch_geoms, warning_geoms = [], []
        watch_union, warning_union = None, None
        for f in geo["features"]:
            feature_type = f["properties"].get("featureType", "")
            if feature_type not in ("tcWarningArea", "tcWatchArea"):
                continue
            area_type = (f["properties"].get("areaType") or "").lower()
            target = warning_geoms if "warning" in area_type else watch_geoms if "watch" in area_type else None
            if target is not None:
                target.append(shapely_shape(f["geometry"]))

        if watch_geoms:
            watch_union = unary_union(watch_geoms)
        if warning_geoms:
            warning_union = unary_union(warning_geoms)
        print(f"[table_a]   -> {len(watch_geoms)} watch polygon(s), {len(warning_geoms)} warning polygon(s)")

        for _, loc in locations.iterrows():
            point = loc.geometry
            rows.append({
                "Disturbance ID":disturbance_id,
                "Base time":pd.to_datetime(fcast_time).tz_localize(None),
                "Location": loc["name"],
                "Watch": bool(watch_union is not None and watch_union.contains(point)),
                "Warning": bool(warning_union is not None and warning_union.contains(point))
                # contains() is strict — a location sitting exactly on a polygon's boundary line (vanishingly unlikely with real coordinates, but technically possible) would return False, not True. Not worth changing unless it actually comes up.
            })
    result = pd.DataFrame(rows, columns = ["Disturbance ID","Base time", "Location", "Watch", "Warning"])
    print(f"[table_a] Done: {len(result)} row(s)")
    return result

def generate_table_b(disturbance_id: str, locations: gpd.GeoDataFrame | None, step_minutes: int = 15) -> pd.DataFrame:
    """
    for every system create the following table at the agreed time interval for all relevant locations. 
    A negative distance to a wind radii means that location is experiencing those winds
    """
    print(f"\n=== Table B: distance-to-wind-radii for {disturbance_id} (step={step_minutes}min) ===")

    if locations is None:
        locations = load_locations()

    rows = []
    df = load_best_track(disturbance_id)   
    interp_df = interpolate_best_track(df, step_minutes=step_minutes)

    n_steps = len(interp_df)
    for i, (_, step) in enumerate(interp_df.iterrows(), start=1):
        if i == 1 or i == n_steps or i % 25 == 0:
            print(f"[table_b] processing time step {i}/{n_steps} ({step.get('TM')})")
        cyc_lat, cyc_lon = step['LAT'], step['LON']
        if pd.isna(cyc_lat) or pd.isna(cyc_lon):
            continue

        for _, loc in locations.iterrows():
            loc_lat, loc_lon = loc.geometry.y, loc.geometry.x
            dist_center_km = calculate_geodesic_distance_km(cyc_lat, cyc_lon, loc_lat, loc_lon)
            
            bearing = get_bearing(cyc_lat, cyc_lon, loc_lat, loc_lon)

            # TODO CHECK IS THIS CORRECT BELOW THESE NEXT SEVEN LINES
            gale_radius_km = get_quadrant_radius(step, "MN_RADIUS_GF", bearing) 
            storm_radius_km = get_quadrant_radius(step, "MN_RADIUS_SF", bearing) 
            hurricane_radius_km = get_quadrant_radius(step, "MN_RADIUS_HF", bearing) 

            
            dist_gale_km = dist_center_km - gale_radius_km
            dist_storm_km = dist_center_km - storm_radius_km
            dist_hurricane_km = dist_center_km - hurricane_radius_km
            
            rows.append({
                "Disturbance ID":disturbance_id,
                "Base time":step["TM"],
                "Location": loc["name"],
                "Uncertainty": step.get("POSITION_UNCERTAINTY", np.nan),
                "Distance to gale": dist_gale_km,
                "Distance to storm": dist_storm_km,
                "Distance to hurricane": dist_hurricane_km,
            })
        
    result = pd.DataFrame(rows, columns = ["Disturbance ID","Base time", "Location", "Uncertainty", "Distance to gale", "Distance to storm", "Distance to hurricane"])
    print(f"[table_b] Done: {len(result)} row(s)")
    return result

def generate_table_c(disturbance_id: str,locations: gpd.GeoDataFrame | None,x_hours: int = 0,y_hours: int = 24,step_minutes: int = 15,table_b: pd.DataFrame | None = None,) -> pd.DataFrame:
    """processed for gales within X to Y hours of the base time

    table_b: pass in an already-computed Table B (e.g. from
    generate_table_b()) to skip recomputing it here -- Table B is the most
    expensive table to build, so generate_all_tables_for_disturbance() passes
    its own copy in rather than letting this function build a second one.
    If you're calling generate_table_c() on its own, leave this as None and
    it'll build Table B for you same as before.
    """
    print(f"\n=== Table C: observed gales within [{x_hours}h, {y_hours}h] of base time for {disturbance_id} ===")
    if locations is None:
        locations = load_locations()

    if table_b is None:
        table_b = generate_table_b(disturbance_id, locations, step_minutes=step_minutes)
    else:
        print("[table_c] Using precomputed Table B (skipping regeneration)")

    if table_b.empty:
        print("[table_c] Table B is empty, returning empty Table C")
        return pd.DataFrame(columns=["Disturbance ID", "Base time", "Location", "Observed"])
    # Work on a copy -- table_b may be a caller-owned DataFrame (passed in to
    # skip regeneration above), and mutating it here would be a unexpected side effect for the caller.
    table_b = table_b.copy()
    table_b["Base time"] = pd.to_datetime(table_b["Base time"]).dt.tz_localize(None)

    fcast_times = get_reference_times(disturbance_id)

    rows = []
    for i, fcast_time in enumerate(fcast_times, start=1):
        base_time = pd.to_datetime(fcast_time)
        if base_time.tzinfo is not None:
            base_time = base_time.tz_localize(None)
        start_window = base_time + pd.Timedelta(hours=x_hours)
        end_window = base_time + pd.Timedelta(hours=y_hours)
        window_df = table_b[
            (table_b["Base time"] >= start_window) & 
            (table_b["Base time"] <= end_window)
        ]
        print(f"[table_c] ({i}/{len(fcast_times)}) base time {fcast_time}: {len(window_df)} best-track row(s) in window")

        for _, loc in locations.iterrows():
            loc_name = loc["name"]
            loc_subset = window_df[window_df["Location"] == loc_name]
            observed = bool((loc_subset["Distance to gale"] <= 0).any()) if not loc_subset.empty else False
            rows.append({
                "Disturbance ID":disturbance_id,
                "Base time":base_time,
                "Location": loc["name"],
                "Observed": observed
            })
    result = pd.DataFrame(rows, columns = ["Disturbance ID","Base time", "Location", "Observed"])
    print(f"[table_c] Done: {len(result)} row(s), {int(result['Observed'].sum()) if not result.empty else 0} observed=True")
    return result

def generate_table_d(table_a: pd.DataFrame, table_c: pd.DataFrame) -> pd.DataFrame:
    
    """this is the base to build the contingency table for the given options."""
    print(f"\n=== Table D: merging Table A ({len(table_a)} rows) with Table C ({len(table_c)} rows) ===")
    merged_table = table_a.merge(table_c, on =["Disturbance ID", "Base time", "Location"], how="left")
    merged_table["Forecast"] = merged_table["Watch"] | merged_table["Warning"]
    merged_table["Observed"] = merged_table["Observed"].fillna(False)
    result = merged_table[["Disturbance ID", "Base time", "Location", "Forecast", "Observed"]]
    print(f"[table_d] Done: {len(result)} row(s)")
    return result


def generate_contingency_dict(table_d: pd.DataFrame, **filters) -> dict:
    """
    Count hit / miss / false alarm / correct negative from Table D, with
    optional column filters applied first (e.g. location="Carnarvon").
    Also returns POD (probability of detection) and FAR (false alarm
    ratio) -- see the earlier discussion on why these are NOT the same
    "probability of gales given a warning" question.
    """
    # TODO CHECK FILTERING WORKS AS INTENDED
    print(f"\n=== Contingency stats (filters={filters or 'none'}) ===")
    df = table_d.copy()

    for key, value in filters.items():
        if key in df.columns:
            df = df[df[key] == value]
    if filters:
        print(f"[stats] {len(df)} row(s) remain after filtering")

    hit = int((df.Forecast & df.Observed).sum())
    false_alarm = int((df.Forecast & ~df.Observed).sum())
    miss = int((~df.Forecast & df.Observed).sum())
    correct_negative = int((~df.Forecast & ~df.Observed).sum())
    total = hit + false_alarm + miss + correct_negative
    results =  {
        "hit": hit,
        "false alarm": false_alarm,
        "miss": miss,
        "correct negative": correct_negative,
        "total": total
    }
    print(f"[stats] {results}")
    return results

def get_contingency_matrix_df(stats: dict) -> pd.DataFrame:
    """
    Takes the dictionary from build_contingency_table and converts it into 
    a formatted 2x2 Contingency Matrix with row/column totals.
    """
    matrix_df = pd.DataFrame(
        data = [
            [stats["hit"], stats["false alarm"], stats["hit"] + stats["false alarm"]],
            [stats["miss"], stats["correct negative"], stats["miss"]+  stats["correct negative"]],
            [stats["hit"] + stats["miss"], stats["false alarm"] + stats["correct negative"], stats["total"]],
        ],
        index = pd.MultiIndex.from_tuples([("Forecast", "Yes"), ("Forecast", "No"), ("Forecast", "Total")]),
        columns = pd.MultiIndex.from_tuples([("Observed", "Yes"), ("Observed", "No"), ("Observed", "Total")])
    )
    return matrix_df

def generate_all_tables_for_disturbance(disturbance_id: str, output_dir: str | Path | None = None, x_hours: int = 0, y_hours: int = 24) -> dict[str, pd.DataFrame | dict]:
    """Generate Tables A-D and the final contingency summary for one disturbance ID."""
    print(f"##### Generating contingency tables for {disturbance_id} #####")
    locations = load_locations()
    table_a = generate_table_a(disturbance_id, locations)
    table_b = generate_table_b(disturbance_id, locations)
    # Pass the Table B we just built straight in, rather than letting
    # generate_table_c() rebuild it from scratch a second time.
    table_c = generate_table_c(disturbance_id, locations, x_hours=x_hours, y_hours=y_hours, table_b=table_b)
    table_d = generate_table_d(table_a, table_c)
    stats = generate_contingency_dict(table_d)
    matrix = get_contingency_matrix_df(stats)

    outputs = {
        "table_a": table_a,
        "table_b": table_b,
        "table_c": table_c,
        "table_d": table_d,
        "stats": stats,
        "matrix": matrix,
    }

    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[write] Writing CSVs to {out_dir} ...")
        for name, frame in (
            ("table_a", table_a),
            ("table_b", table_b),
            ("table_c", table_c),
            ("table_d", table_d),
            ("contingency_matrix", matrix.reset_index()),
        ):
            out_path = out_dir / f"{disturbance_id}_{name}.csv"
            frame.to_csv(out_path, index=False)
            print(f"[write]   {out_path} ({len(frame)} row(s))")

        summary_path = out_dir / f"{disturbance_id}_contingency_summary.csv"
        pd.DataFrame([stats]).to_csv(summary_path, index=False)
        print(f"[write]   {summary_path}")

    print(f"##### Done: {disturbance_id} #####\n")
    return outputs

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate contingency tables and summary CSVs for a cyclone disturbance ID.")
    parser.add_argument("disturbance_id", help="BOM disturbance ID, for example AU202526_34U")
    parser.add_argument("--output-dir", default="data/contingency_tables", help="Directory to write the generated CSV tables to")
    parser.add_argument("--x-hours", type=int, default=0, help="Lower bound for observed-gale window in hours")
    parser.add_argument("--y-hours", type=int, default=24, help="Upper bound for observed-gale window in hours")
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    try:
        outputs = generate_all_tables_for_disturbance(
            args.disturbance_id,
            output_dir=args.output_dir,
            x_hours=args.x_hours,
            y_hours=args.y_hours,
        )
        print(f"Generated contingency tables for {args.disturbance_id}")
        print(outputs["stats"])
        print("\nContingency matrix:")
        print(outputs["matrix"])
    except Exception as exc:  # pragma: no cover - CLI safety path
        raise SystemExit(f"Failed to generate contingency tables for {args.disturbance_id}: {exc}")