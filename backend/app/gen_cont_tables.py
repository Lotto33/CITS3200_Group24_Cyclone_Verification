import argparse
import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString
from shapely.geometry import shape as shapely_shape
from shapely.ops import nearest_points, unary_union
from shapely.validation import make_valid

geod = Geod(ellps="WGS84")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_DIR = PROJECT_ROOT / "data" / "geojson"
BEST_TRACK_CSV = PROJECT_ROOT / "data" / "best_track.csv"
BEST_TRACK_INTERPOLATED_CSV = (
    PROJECT_ROOT / "data" / "processed" / "best_track_interpolated.csv"
)
# Location/state source for Table A. The TC Locations sheet is authoritative;
# data/towns.csv is not read by this pipeline (and is currently an Excel
# workbook despite its .csv filename).
TOWNS_XLSX = Path(__file__).resolve().parent / "resources" / "towns.xlsx"
BEST_TRACK_SKIPROWS = 4  # 3 copyright lines + 1 blank before the header

# A town counts as coastal if this column has a value in the TC Locations
# sheet. The State column from that same sheet is carried into Table A and D.
COASTAL_ORDER_COLUMN = "Coastal Order"
# The 20 km rule applies to the coastal buffer: for coastal towns, being
# within 20 km of a watch/warning polygon edge counts as covered, even if the
# town is not strictly inside the polygon. This is a different rule from the
# 300 km relevance filter, which decides whether a town appears in Table A at
# all because it is close enough to any watch/warning area.
DEFAULT_COASTAL_BUFFER_KM = 20.0
# The coastal buffer only applies to forecasts issued before this date --
# the threat-area creation methodology changed from this point on, so
# post-change polygons don't have the town-A-to-town-B gap problem the
# buffer was compensating for. Forecasts at or after this date are treated
# as strict polygon containment only, regardless of coastal status.
DEFAULT_COASTAL_BUFFER_CUTOFF = pd.Timestamp("2025-06-01")
# Towns only appear in Table A if within this distance of a watch OR
# warning area (scope doc S43).
DEFAULT_RELEVANCE_KM = 300.0

# Observations beyond max(100 km, position uncertainty) of every wind radius
# are omitted from Table B; Table D treats missing observations as no gales.
DISTANCE_CUTOFF_MIN_KM = 100.0

# Columns that interpolate normally (continuous quantities)
LINEAR_COLS = ["LAT", "LON", "MAX_WIND_SPD", "POSITION_UNCERTAINTY", "CENTRAL_PRES"]
# GF = galeforce
# HF = hurricane force
# SF = Storm force

RADIUS_COLS = [
    "MN_RADIUS_GF_WIND",
    "MN_RADIUS_GF_SECNE",
    "MN_RADIUS_GF_SECSE",
    "MN_RADIUS_GF_SECSW",
    "MN_RADIUS_GF_SECNW",
    "MN_RADIUS_SF_WIND",
    "MN_RADIUS_SF_SECNE",
    "MN_RADIUS_SF_SECSE",
    "MN_RADIUS_SF_SECSW",
    "MN_RADIUS_SF_SECNW",
    "MN_RADIUS_HF_WIND",
    "MN_RADIUS_HF_SECNE",
    "MN_RADIUS_HF_SECSE",
    "MN_RADIUS_HF_SECSW",
    "MN_RADIUS_HF_SECNW",
]
_geojson_index_cache: dict | None = None
_best_track_cache: pd.DataFrame | None = (
    None  # TODO make some way to udate this cache when new dataset is added
)
_best_track_cache_path: Path | None = None


def _best_track_source_path() -> Path:
    """Use the ETL output when available, otherwise fall back to raw data."""
    return (
        BEST_TRACK_INTERPOLATED_CSV
        if BEST_TRACK_INTERPOLATED_CSV.is_file()
        else BEST_TRACK_CSV
    )


def _best_track_is_preprocessed() -> bool:
    return _best_track_source_path() == BEST_TRACK_INTERPOLATED_CSV


def announce_best_track_source() -> None:

    source_path = _best_track_source_path()
    if source_path == BEST_TRACK_INTERPOLATED_CSV:
        print(f"[best_track] Using interpolated CSV: {source_path}")
        print("[best_track] Local interpolation will be skipped")
    else:
        print(f"[best_track] Interpolated CSV not found; using raw CSV: {source_path}")
        print("[best_track] Local interpolation will be performed")


# NOTE pd.DataFrame A collection of labelled columns, where each column is essentially an array of values.
def load_full_best_track() -> pd.DataFrame:
    global _best_track_cache, _best_track_cache_path
    source_path = _best_track_source_path()
    if _best_track_cache is None or _best_track_cache_path != source_path:
        print(f"[best_track] Loading {source_path} ...")
        read_options = {"low_memory": False}
        if source_path == BEST_TRACK_CSV:
            read_options["skiprows"] = BEST_TRACK_SKIPROWS
        _best_track_cache = pd.read_csv(source_path, **read_options)
        _best_track_cache_path = source_path
        print(
            f"[best_track] Loaded {len(_best_track_cache)} rows from {source_path.name}"
        )
    return _best_track_cache


def load_best_track(cyclone_id: str) -> pd.DataFrame:
    df = load_full_best_track()
    df = df[df.DISTURBANCE_ID == cyclone_id].copy()
    print(f"[best_track] {len(df)} row(s) matched DISTURBANCE_ID == {cyclone_id!r}")
    df["TM"] = pd.to_datetime(df["TM"])
    # LINEAR_COLS assumes the raw BOM CSV's fixed schema. The preprocessed
    # best_track_interpolated.csv (see _best_track_is_preprocessed) may not
    # carry every one of these columns (e.g. CENTRAL_PRES) -- coerce only
    # the ones actually present rather than crashing on df[col] for a
    # missing one, and say so loudly since a silently-missing column here
    # would otherwise just look like a KeyError with no context.
    missing_linear_cols = [col for col in LINEAR_COLS if col not in df.columns]
    if missing_linear_cols:
        print(
            f"[best_track] WARNING: column(s) {missing_linear_cols} not present in this best-track source, "
            f"skipping numeric coercion for them. Available columns: {list(df.columns)}"
        )
    for col in LINEAR_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("TM").reset_index(drop=True)


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
    forward = obs_times.reindex(series.index, method="ffill")
    backward = obs_times.reindex(series.index, method="bfill")
    forward_dist = (series.index.to_series() - forward).abs()
    backward_dist = (backward - series.index.to_series()).abs()
    forward_vals = observed.reindex(series.index, method="ffill")
    backward_vals = observed.reindex(series.index, method="bfill")
    # NaT comparisons are always False regardless of direction, so a plain
    # forward_dist <= backward_dist silently prefers "backward" whenever
    # backward_dist is NaT -- i.e. whenever there's no future observation to
    # backward-fill from at all (the trailing edge of the series). That
    # picks backward_vals (NaN there) instead of the perfectly valid
    # forward_vals. Handle "only one direction actually exists" explicitly
    # rather than relying on the NaT comparison to do the right thing.
    has_forward = forward.notna()
    has_backward = backward.notna()
    use_forward = has_forward & (~has_backward | (forward_dist <= backward_dist))
    return forward_vals.where(use_forward, backward_vals)


def interpolate_best_track(df: pd.DataFrame, step_minutes: int = 15) -> pd.DataFrame:
    # NOTE THIS FUNCTION IS TEMPORARY. USE SIYUS VIA IMPORT -> TODO
    if df.empty:
        print(
            "[interpolate_best_track] Input best-track slice is empty, nothing to interpolate"
        )
        return df

    indexed = df.set_index("TM")

    # Build a regular grid, merged with the original observation timestamps
    # so you don't lose the real observed points.
    grid = pd.date_range(
        indexed.index.min(), indexed.index.max(), freq=f"{step_minutes}min"
    )
    full_index = indexed.index.union(grid).sort_values()
    reindexed = indexed.reindex(full_index)

    for col in LINEAR_COLS:
        # limit_direction="both" extends the nearest known value out to the
        # track's start/end edges (there's nothing to genuinely interpolate
        # beyond the first/last observation). Without this, a field like
        # POSITION_UNCERTAINTY that's missing on the very first or last real
        # fix stays NaN for every interpolated step before/after it, even
        # though RADIUS_COLS below don't have that gap (they use
        # _nearest_observed_fill, which already reaches the edges).
        reindexed[col] = pd.to_numeric(reindexed[col], errors="coerce").interpolate(
            method="time", limit_direction="both"
        )
    for col in RADIUS_COLS:
        reindexed[col] = _nearest_observed_fill(
            pd.to_numeric(reindexed[col], errors="coerce")
        )

    reindexed = reindexed.reset_index().rename(columns={"index": "TM"})
    result = reindexed[reindexed.TM.isin(grid)].reset_index(drop=True)
    print(
        f"[interpolate_best_track] {len(df)} observed rows -> {len(result)} rows at {step_minutes}min steps"
    )
    return result


def load_locations() -> gpd.GeoDataFrame:
    """
    Real BOM locations list. Latitude/Longitude are plain WGS84 degrees
    already -- no reprojection needed, unlike the earlier GIS towns layer.
    """
    print(
        f"[locations] Loading {TOWNS_XLSX} (sheet 'TC Locations'; State/coordinates source) ..."
    )
    df = pd.read_excel(TOWNS_XLSX, sheet_name="TC Locations")
    print(f"[locations] Loaded {len(df)} raw row(s)")

    # The sheet has blank separator rows between town groups (Name/State/
    # Latitude/Longitude all empty). These become Point(NaN, NaN) geometries,
    # which GEOS raises an (unhelpfully blank-message) exception on as soon
    # as any contains()/distance/nearest_points check touches them -- so
    # they need to be dropped here, not silently carried through.
    valid = df["Name"].notna() & df["Latitude"].notna() & df["Longitude"].notna()
    n_dropped = int((~valid).sum())
    if n_dropped:
        print(
            f"[locations] Dropping {n_dropped} row(s) with missing Name/Latitude/Longitude (blank separator rows)"
        )
    df = df[valid].reset_index(drop=True)
    print(f"[locations] {len(df)} usable location(s)")

    if COASTAL_ORDER_COLUMN in df.columns:
        is_coastal = df[COASTAL_ORDER_COLUMN].notna()
        print(
            f"[locations] {int(is_coastal.sum())} coastal location(s) (have a {COASTAL_ORDER_COLUMN!r} value)"
        )
    else:
        print(
            f"[locations] WARNING: column {COASTAL_ORDER_COLUMN!r} not found in the TC Locations sheet -- "
            f"treating every location as non-coastal, so the coastal buffer will never apply. "
            f"Available columns: {list(df.columns)}"
        )
        is_coastal = pd.Series(False, index=df.index)
    return gpd.GeoDataFrame(
        {"name": df["Name"], "state": df["State"], "is_coastal": is_coastal},
        geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
        crs="EPSG:4283",
    )


def calculate_geodesic_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
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
    Returns NaN (not 0.0) if neither value was ever recorded for this
    intensity level at this time step -- "no data" and "radius is genuinely
    zero" are different things, and treating them the same silently implies
    a location has no gale/storm/hurricane exposure when the truth is we
    simply don't know, which understates the system's actual reach.
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

    return np.nan


def _beyond_observation_cutoff(
    uncertainty_km: float,
    gale_distance_km: float,
) -> bool:
    """Whether a Table B row should be omitted.

    A missing gale distance means no gale radius was recorded (max wind below
    gale force), so the row can never be an observed gale. Otherwise the row is
    omitted when the gale distance exceeds max(100 km, uncertainty); storm and
    hurricane radii are nested inside the gale radius and ignored.
    """
    if pd.isna(gale_distance_km) or not np.isfinite(gale_distance_km):
        return True
    cutoff_km = DISTANCE_CUTOFF_MIN_KM
    if pd.notna(uncertainty_km) and np.isfinite(uncertainty_km):
        cutoff_km = max(cutoff_km, float(uncertainty_km))
    return gale_distance_km > cutoff_km


def signed_distance_to_polygon_km(point, polygon_union) -> float:
    """Geodesic distance in km from point to the nearest edge of
    polygon_union. Negative when point is inside the polygon, matching
    Table B's "negative = experiencing the wind" convention. NaN if
    polygon_union is None (e.g. no watch area was issued for this bulletin
    at all, as opposed to one existing a long way away)."""
    if polygon_union is None:
        return np.nan
    nearest_on_boundary, _ = nearest_points(polygon_union.boundary, point)
    dist_km = calculate_geodesic_distance_km(
        point.y, point.x, nearest_on_boundary.y, nearest_on_boundary.x
    )
    return -dist_km if polygon_union.contains(point) else dist_km


def _valid_polygonal(geom):
    """Repair a self-intersecting polygon, keeping only its areal parts.

    ~2% of the BoM watch/warning polygons self-intersect, which makes
    unary_union raise a TopologyException. make_valid can return a
    GeometryCollection with stray lines, whose .boundary is None, so those
    parts are dropped.
    """
    if geom.is_valid:
        return geom
    fixed = make_valid(geom)
    parts = getattr(fixed, "geoms", [fixed])
    return unary_union([p for p in parts if p.geom_type in ("Polygon", "MultiPolygon")])


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
        print(
            f"[geojson_index] Found {scanned} file(s), indexed {len(_geojson_index_cache)} unique (distId, fcastTime) key(s)"
        )
        if scanned == 0:
            print(
                f"[geojson_index] WARNING: no .geojson files found under {GEOJSON_DIR} -- did you run build_gml_dataset.py?"
            )
    return _geojson_index_cache


def load_forecast_geojson(disturbance_id: str, fcast_time: str) -> dict | None:
    path = _geojson_index().get((disturbance_id, fcast_time))
    if path is None:
        print(
            f"[load_forecast_geojson] No file indexed for ({disturbance_id!r}, {fcast_time!r})"
        )
        return None
    return json.loads(path.read_text())


def find_pre_cutoff_near_polygon_distances(
    locations: gpd.GeoDataFrame | None = None,
    cutoff: pd.Timestamp = DEFAULT_COASTAL_BUFFER_CUTOFF,
    max_distance_km: float = DEFAULT_COASTAL_BUFFER_KM,
    output_csv: str | Path | None = None,
) -> pd.DataFrame:
    """Find towns that are just outside pre-cutoff watch/warning polygons.

    Every forecast bulletin for every cyclone is checked. Only locations
    marked coastal by ``load_locations()`` (the TC Locations sheet's
    ``Coastal Order`` column) are considered. A result is created for each
    coastal town-to-polygon-type distance where the town is outside the
    polygon (distance > 0) and strictly closer than ``max_distance_km``.
    Therefore, a town can produce two rows for one bulletin: one for a watch
    and one for a warning. ``Nearby area count`` reports how many qualifying
    watch/warning distances that town has for that cyclone and bulletin.

    If ``output_csv`` is supplied, the same results are also written to a
    CSV file. This is an analysis/reporting function; it does not change
    Table A's relevance filtering or coastal coverage decisions.
    """
    if max_distance_km <= 0:
        raise ValueError("max_distance_km must be greater than 0")

    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is not None:
        cutoff = cutoff.tz_localize(None)
    if locations is None:
        locations = load_locations()

    columns = [
        "Disturbance ID",
        "Base time",
        "Location",
        "Area type",
        "Distance (km)",
        "Nearby area count",
    ]
    matches: list[dict] = []

    for disturbance_id in list_available_disturbance_ids():
        for fcast_time in get_reference_times(disturbance_id):
            base_time = pd.Timestamp(fcast_time)
            if base_time.tzinfo is not None:
                base_time = base_time.tz_localize(None)
            if base_time >= cutoff:
                continue

            geo = load_forecast_geojson(disturbance_id, fcast_time)
            if geo is None:
                continue

            polygon_unions = {"Watch": None, "Warning": None}
            geometries = {"Watch": [], "Warning": []}
            for feature in geo.get("features", []):
                properties = feature.get("properties", {})
                if properties.get("featureType") not in (
                    "tcWarningArea",
                    "tcWatchArea",
                ):
                    continue
                area_type = (properties.get("areaType") or "").lower()
                area_name = (
                    "Warning"
                    if "warning" in area_type
                    else "Watch"
                    if "watch" in area_type
                    else None
                )
                if area_name is not None:
                    geometries[area_name].append(shapely_shape(feature["geometry"]))

            for area_name, area_geometries in geometries.items():
                if area_geometries:
                    polygon_unions[area_name] = unary_union(area_geometries)

            bulletin_matches: list[dict] = []
            for _, location in locations.iterrows():
                if not bool(location.get("is_coastal", False)):
                    continue
                for area_name, polygon_union in polygon_unions.items():
                    distance = signed_distance_to_polygon_km(
                        location.geometry, polygon_union
                    )
                    if pd.notna(distance) and 0 < distance < max_distance_km:
                        bulletin_matches.append(
                            {
                                "Disturbance ID": disturbance_id,
                                "Base time": base_time,
                                "Location": location["name"],
                                "Area type": area_name,
                                "Distance (km)": distance,
                            }
                        )

            if bulletin_matches:
                counts = pd.Series(
                    [match["Location"] for match in bulletin_matches]
                ).value_counts()
                for match in bulletin_matches:
                    match["Nearby area count"] = int(counts[match["Location"]])
                matches.extend(bulletin_matches)

    result = pd.DataFrame(matches, columns=columns)

    if output_csv is not None:
        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(
            f"[near_polygon_report] Wrote {len(result)} matching distance(s) to {output_path}"
        )

    return result


def get_best_track_geojson(cyclone_id: str) -> dict | None:
    raw = load_best_track(cyclone_id)
    if raw.empty:
        print(
            f"[get_best_track_geojson] No best-track rows for {cyclone_id!r}, returning None"
        )
        return None

    interpolated_data = (
        raw if _best_track_is_preprocessed() else interpolate_best_track(raw)
    )
    interpolated_data = interpolated_data.dropna(subset=["LAT", "LON"])

    line = LineString(zip(interpolated_data.LON, interpolated_data.LAT, strict=True))
    gdf = gpd.GeoDataFrame(
        [{"disturbance_id": cyclone_id}], geometry=[line], crs="EPSG:4283"
    )
    return gdf.__geo_interface__["features"][0]


def get_reference_times(disturbance_id: str) -> list[str]:
    times = sorted(
        fcast_time
        for (dist_id, fcast_time) in _geojson_index()
        if disturbance_id == dist_id and fcast_time
    )
    print(
        f"[get_reference_times] {len(times)} forecast base time(s) found for {disturbance_id!r}"
    )
    return times


def derive_season(base_time) -> str:
    """Derive the Jul-Jun cyclone season label (e.g. '2025-26') from a
    timestamp. Months Jul-Dec belong to the season starting that year;
    months Jan-Jun belong to the season that started the previous year."""
    ts = pd.Timestamp(base_time)
    start_year = ts.year if ts.month >= 7 else ts.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def list_available_disturbance_ids() -> list[str]:
    """Every distinct disturbance ID that has at least one forecast geojson
    file indexed under GEOJSON_DIR."""
    ids = sorted({dist_id for (dist_id, _fcast_time) in _geojson_index() if dist_id})
    print(f"[list_available_disturbance_ids] {len(ids)} disturbance(s) available")
    return ids


def list_disturbance_ids_for_season(season: str) -> list[str]:
    """Find every disturbance ID with at least one forecast base time
    (fcastTime) falling in the given Jul-Jun season, e.g. '2025-26'."""
    ids = set()
    for dist_id, fcast_time in _geojson_index():
        if not dist_id or not fcast_time:
            continue
        if derive_season(fcast_time) == season:
            ids.add(dist_id)
    result = sorted(ids)
    print(
        f"[list_disturbance_ids_for_season] season {season!r}: {len(result)} disturbance(s) -> {result}"
    )
    return result


def filter_base_times(
    fcast_times: list[str], base_time_hours: list[int] | None
) -> list[str]:
    """Keep only forecast timestamps whose UTC hour is selected."""
    if base_time_hours is None:
        return sorted(fcast_times)
    selected = set(base_time_hours)
    return [
        fcast_time
        for fcast_time in sorted(fcast_times)
        if pd.to_datetime(fcast_time, utc=True).hour in selected
    ]


"""See the client's scope and deliverables"""


def generate_table_a(
    disturbance_id: str,
    locations: gpd.GeoDataFrame | None,
    coastal_buffer_km: float = DEFAULT_COASTAL_BUFFER_KM,
    relevance_km: float = DEFAULT_RELEVANCE_KM,
    coastal_buffer_cutoff: pd.Timestamp = DEFAULT_COASTAL_BUFFER_CUTOFF,
    forecasts: dict[str, dict] | None = None,
    fcast_times: list[str] | None = None,
    base_time_hours: list[int] | None = None,
) -> pd.DataFrame:
    """
    create a table from the forecast polygons for each forecast base time including relevant locations

    Distance to watch / Distance to warning: geodesic km from the location
    to the nearest edge of the watch/warning polygon, negative if the
    location is inside it (same sign convention as Table B). NaN if no
    polygon of that type was issued for this base time.

    Watch/Warning are True if the location is inside the polygon (distance
    <= 0), OR -- for coastal towns only (towns.xlsx's Coastal Order column
    has a value), and only for bulletins issued before coastal_buffer_cutoff
    -- if it's within coastal_buffer_km of the polygon edge. This buffer
    exists because the old town-A-to-town-B coastal zone definitions didn't
    overlap, so edge towns weren't always technically inside the polygon
    even though they should count as covered. The threat-area creation
    methodology changed at coastal_buffer_cutoff, so bulletins from that
    date onward don't have this gap and get strict containment only,
    coastal or not.

    For coastal towns with the buffer applied, Watch and Warning are
    mutually exclusive: Warning takes priority. If the town is within coastal_buffer_km of the warning polygon, it's
    Warning only, regardless of its distance to any watch polygon. Watch is
    only considered if that warning condition doesn't hold. Non-coastal
    towns (and coastal towns on/after coastal_buffer_cutoff) don't get this
    exclusivity -- Watch and Warning are evaluated independently via strict
    containment only, and can both be True if the town is genuinely inside
    two overlapping polygons.

    A location only appears in the output at all if its minimum distance to
    a watch OR warning polygon is under relevance_km. This is separate from
    the coastal buffer rule below, which decides whether a coastal town is
    treated as covered when the nearest watch/warning edge is within
    coastal_buffer_km (default 20 km).

    forecasts: {fcastTime: FeatureCollection} to use instead of scanning
    data/geojson -- the database-backed verification loader passes these in.
    """
    print(f"\n=== Table A: forecast watch/warning areas for {disturbance_id} ===")
    if locations is None:
        locations = load_locations()
    rows = []
    if forecasts is not None:
        available_times = sorted(forecasts)
    elif fcast_times is not None:
        available_times = fcast_times
    else:
        available_times = get_reference_times(disturbance_id)
    selected_times = filter_base_times(available_times, base_time_hours)
    for i, fcast_time in enumerate(selected_times, start=1):
        print(f"[table_a] ({i}/{len(selected_times)}) base time {fcast_time}")
        if forecasts is not None:
            geo = forecasts[fcast_time]
        else:
            geo = load_forecast_geojson(disturbance_id, fcast_time)
        if geo is None:
            print("[table_a]   -> no geojson found, skipping this base time")
            continue

        base_time_dt = pd.to_datetime(fcast_time).tz_localize(None)
        buffer_applies = base_time_dt < coastal_buffer_cutoff
        if not buffer_applies:
            print(
                f"[table_a]   -> base time is on/after {coastal_buffer_cutoff.date()}, coastal buffer disabled for this bulletin"
            )

        # This bulletin's own declared validity period is used later by
        # generate_table_c, not here -- Table A's schema doesn't include it.
        watch_geoms, warning_geoms = [], []
        watch_union, warning_union = None, None
        for f in geo["features"]:
            feature_type = f["properties"].get("featureType", "")
            if feature_type not in ("tcWarningArea", "tcWatchArea"):
                continue
            area_type = (f["properties"].get("areaType") or "").lower()
            target = (
                warning_geoms
                if "warning" in area_type
                else watch_geoms
                if "watch" in area_type
                else None
            )
            if target is not None:
                target.append(_valid_polygonal(shapely_shape(f["geometry"])))

        if watch_geoms:
            watch_union = unary_union(watch_geoms)
        if warning_geoms:
            warning_union = unary_union(warning_geoms)
        print(
            f"[table_a]   -> {len(watch_geoms)} watch polygon(s), {len(warning_geoms)} warning polygon(s)"
        )

        kept = 0
        for _, loc in locations.iterrows():
            point = loc.geometry
            dist_watch = signed_distance_to_polygon_km(point, watch_union)
            dist_warning = signed_distance_to_polygon_km(point, warning_union)

            candidate_distances = [d for d in (dist_watch, dist_warning) if pd.notna(d)]
            if not candidate_distances or min(candidate_distances) >= relevance_km:
                continue  # more than relevance_km from any watch/warning area (or neither exists) -- not relevant here

            # Coastal coverage uses the nearest boundary distance to any watch/warning polygon.
            # This is intentionally different from the relevance_km gate above: the 300 km check
            # decides whether a town appears in the table at all, while the 20 km buffer decides
            # whether a coastal town is treated as covered when it sits just outside the polygon.
            is_coastal = bool(loc.get("is_coastal", False)) and buffer_applies
            if is_coastal:
                # a coastal town should never be classified as both Watch and Warning at once. Warning takes
                # priority if the town is within coastal_buffer_km of the
                # warning polygon (this also covers strict containment, since
                # being inside gives a distance <= 0, which is always within
                # the buffer), it's Warning only. Watch is only checked if
                # that Warning condition doesn't hold.
                warning = bool(
                    pd.notna(dist_warning) and dist_warning <= coastal_buffer_km
                )
                watch = bool(
                    not warning
                    and pd.notna(dist_watch)
                    and dist_watch <= coastal_buffer_km
                )
            else:
                # Non-coastal towns (or coastal towns on/after the buffer
                # cutoff date): strict polygon containment only, evaluated
                # independently -- both can legitimately be True if the town
                # is genuinely inside two overlapping polygons.
                watch = bool(pd.notna(dist_watch) and dist_watch <= 0)
                warning = bool(pd.notna(dist_warning) and dist_warning <= 0)

            rows.append(
                {
                    "Disturbance ID": disturbance_id,
                    "Base time": base_time_dt,
                    "Location": loc["name"],
                    "Distance to watch": dist_watch,
                    "Distance to warning": dist_warning,
                    "Watch": watch,
                    "Warning": warning,
                    # contains() (via signed_distance_to_polygon_km's use of polygon_union.contains)
                    # is strict -- a location sitting exactly on a polygon's boundary line
                    # (vanishingly unlikely with real coordinates, but technically possible)
                    # would come out as outside with distance 0, not inside. Not worth
                    # changing unless it actually comes up.
                }
            )
            kept += 1
        print(
            f"[table_a]   -> {kept} location(s) within {relevance_km}km (of {len(locations)} total)"
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "Disturbance ID",
            "Base time",
            "Location",
            "Distance to watch",
            "Distance to warning",
            "Watch",
            "Warning",
        ],
    )
    print(f"[table_a] Done: {len(result)} row(s)")
    return result


def generate_table_b(
    disturbance_id: str,
    locations: gpd.GeoDataFrame | None,
    step_minutes: int = 15,
    track: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    for every system create the following table at the agreed time interval for all relevant locations.
    A negative distance to a wind radii means that location is experiencing those winds.

    `locations` should already be filtered down to the "relevant" locations
    for this disturbance -- i.e. those appearing in Table A -- rather than
    every town in towns.xlsx. generate_all_tables_for_disturbance() does
    this filtering before calling in; pass a pre-filtered GeoDataFrame here
    if calling this directly.

    track: an already-interpolated best track for this disturbance (the
    database-backed verification loader passes one in); None reads the CSVs.
    """
    print(
        f"\n=== Table B: distance-to-wind-radii for {disturbance_id} (step={step_minutes}min) ==="
    )

    if locations is None:
        locations = load_locations()

    rows = []
    cutoff_rows = 0
    df = track if track is not None else load_best_track(disturbance_id)
    if track is not None or _best_track_is_preprocessed():
        print(
            "[table_b] Using pre-interpolated best-track data (skipping interpolation)"
        )
        # Interpolation itself is skipped, but numeric dtypes still need to
        # be guaranteed -- interpolate_best_track() is normally what coerces
        # RADIUS_COLS to numeric, and skipping it entirely would leave those
        # columns as whatever dtype pandas guessed from the CSV (risking a
        # TypeError later in get_quadrant_radius()'s `val > 0` comparison if
        # any come through as strings).
        interp_df = df.copy()
        for col in LINEAR_COLS + RADIUS_COLS:
            if col in interp_df.columns:
                interp_df[col] = pd.to_numeric(interp_df[col], errors="coerce")
    else:
        interp_df = interpolate_best_track(df, step_minutes=step_minutes)

    n_steps = len(interp_df)
    for i, (_, step) in enumerate(interp_df.iterrows(), start=1):
        if i == 1 or i == n_steps or i % 25 == 0:
            print(f"[table_b] processing time step {i}/{n_steps} ({step.get('TM')})")
        cyc_lat, cyc_lon = step["LAT"], step["LON"]
        if pd.isna(cyc_lat) or pd.isna(cyc_lon):
            continue

        for _, loc in locations.iterrows():
            loc_lat, loc_lon = loc.geometry.y, loc.geometry.x
            dist_center_km = calculate_geodesic_distance_km(
                cyc_lat, cyc_lon, loc_lat, loc_lon
            )

            bearing = get_bearing(cyc_lat, cyc_lon, loc_lat, loc_lon)

            # TODO CHECK IS THIS CORRECT BELOW THESE NEXT SEVEN LINES
            gale_radius_km = get_quadrant_radius(step, "MN_RADIUS_GF", bearing)
            storm_radius_km = get_quadrant_radius(step, "MN_RADIUS_SF", bearing)
            hurricane_radius_km = get_quadrant_radius(step, "MN_RADIUS_HF", bearing)

            dist_gale_km = dist_center_km - gale_radius_km
            dist_storm_km = dist_center_km - storm_radius_km
            dist_hurricane_km = dist_center_km - hurricane_radius_km

            uncertainty_km = step.get("POSITION_UNCERTAINTY", np.nan)
            if _beyond_observation_cutoff(uncertainty_km, dist_gale_km):
                cutoff_rows += 1
                continue

            rows.append(
                {
                    "Disturbance ID": disturbance_id,
                    "Location": loc["name"],
                    "Time": step["TM"],
                    "Analysis Uncertainty": uncertainty_km,
                    "Distance to gale": dist_gale_km,
                    "Distance to storm": dist_storm_km,
                    "Distance to hurricane": dist_hurricane_km,
                }
            )

    result = pd.DataFrame(
        rows,
        columns=[
            "Disturbance ID",
            "Location",
            "Time",
            "Analysis Uncertainty",
            "Distance to gale",
            "Distance to storm",
            "Distance to hurricane",
        ],
    )
    print(
        f"[table_b] Done: {len(result)} row(s); "
        f"{cutoff_rows} beyond the max(100 km, position uncertainty) cutoff omitted"
    )
    return result


def generate_table_c(
    disturbance_id: str,
    locations: gpd.GeoDataFrame | None,
    x_hours: int = 0,
    y_hours: int = 24,
    wind_level: str = "gale",
    step_minutes: int = 15,
    table_b: pd.DataFrame | None = None,
    fcast_times: list[str] | None = None,
) -> pd.DataFrame:
    """processed for gales within X to Y hours of the base time

    table_b: pass in an already-computed Table B (e.g. from
    generate_table_b()) to skip recomputing it here -- Table B is the most
    expensive table to build, so generate_all_tables_for_disturbance() passes
    its own copy in rather than letting this function build a second one.
    If you're calling generate_table_c() on its own, leave this as None and
    it'll build Table B for you same as before.

    x_hours/y_hours define "the Warning/Watch time range" as a fixed window
    relative to each base time -- confirmed by the client as: Warning = 0 to
    24 hours (the default), Watch = 24 to 48 hours. This is NOT derived from
    each bulletin's own declared expiryHrs field; that was an earlier
    assumption that turned out to be wrong. Other windows (e.g. 0-30h, 0-42h)
    can be explored by passing different x_hours/y_hours values.
    """
    distance_columns = {
        "gale": "Distance to gale",
        "storm": "Distance to storm",
        "hurricane": "Distance to hurricane",
    }

    if wind_level not in distance_columns:
        raise ValueError(
            f"Invalid wind level {wind_level!r}. "
            f"Expected one of {list(distance_columns)}"
        )

    distance_column = distance_columns[wind_level]

    print(
        f"\n=== Table C: observed {wind_level} winds within [{x_hours}h, {y_hours}h] of base time for {disturbance_id} ==="
    )
    if locations is None:
        locations = load_locations()

    if table_b is None:
        table_b = generate_table_b(disturbance_id, locations, step_minutes=step_minutes)
    else:
        print("[table_c] Using precomputed Table B (skipping regeneration)")

    if table_b.empty:
        print("[table_c] Table B is empty, returning empty Table C")
        return pd.DataFrame(
            columns=["Disturbance ID", "Base time", "Location", "Observed"]
        )
    # Work on a copy -- table_b may be a caller-owned DataFrame (passed in to
    # skip regeneration above), and mutating it here would be a surprising
    # side effect for the caller.
    table_b = table_b.copy()
    table_b["Time"] = pd.to_datetime(table_b["Time"]).dt.tz_localize(None)

    if fcast_times is None:
        fcast_times = get_reference_times(disturbance_id)

    rows = []
    for i, fcast_time in enumerate(fcast_times, start=1):
        base_time = pd.to_datetime(fcast_time)
        if base_time.tzinfo is not None:
            base_time = base_time.tz_localize(None)

        start_window = base_time + pd.Timedelta(hours=x_hours)
        end_window = base_time + pd.Timedelta(hours=y_hours)
        window_df = table_b[
            (table_b["Time"] >= start_window) & (table_b["Time"] <= end_window)
        ]
        print(
            f"[table_c] ({i}/{len(fcast_times)}) base time {fcast_time}: {len(window_df)} best-track row(s) in window"
        )

        for _, loc in locations.iterrows():
            loc_name = loc["name"]
            loc_subset = window_df[window_df["Location"] == loc_name]
            observed = (
                bool((loc_subset[distance_column] <= 0).any())
                if not loc_subset.empty
                else False
            )
            rows.append(
                {
                    "Disturbance ID": disturbance_id,
                    "Base time": base_time,
                    "Location": loc["name"],
                    "Observed": observed,
                }
            )
    result = pd.DataFrame(
        rows, columns=["Disturbance ID", "Base time", "Location", "Observed"]
    )
    print(
        f"[table_c] Done: {len(result)} row(s), {int(result['Observed'].sum()) if not result.empty else 0} observed=True"
    )
    return result


def generate_table_d(table_a: pd.DataFrame, table_c: pd.DataFrame, forecast_level: str = "watch_warning",) -> pd.DataFrame:
    """this is the base to build the contingency table for the given options."""

    print(
        f"\n=== Table D: merging Table A ({len(table_a)} rows) with Table C ({len(table_c)} rows) ==="
    )
    merged_table = table_a.merge(
        table_c, on=["Disturbance ID", "Base time", "Location"], how="left"
    )

    if forecast_level == "watch_warning":
        merged_table["Forecast"] = merged_table["Watch"] | merged_table["Warning"]
    elif forecast_level == "watch":
        merged_table["Forecast"] = merged_table["Watch"]
    elif forecast_level == "warning":
        merged_table["Forecast"] = merged_table["Warning"]
    else:
        raise ValueError(
            f"Invalid forecast level {forecast_level!r}. "
            "Expected one of ['watch_warning', 'watch', 'warning']"
        )
    
    merged_table["Observed"] = merged_table["Observed"].fillna(False)
    # Derived purely from Base time -- lets contingency stats be filtered by
    # cyclone season (e.g. Season="2025-26") without needing a separate
    # season lookup table. State is intentionally not retained in Table D;
    # state filtering happens before Table A is generated.
    merged_table["Season"] = merged_table["Base time"].apply(derive_season)
    result_columns = [
        "Disturbance ID",
        "Base time",
        "Location",
        "Season",
        "Forecast",
        "Observed",
    ]
    result = merged_table[result_columns]
    print(f"[table_d] Done: {len(result)} row(s)")
    return result


def generate_contingency_dict(table_d: pd.DataFrame, **filters) -> dict:
    """
    Count hit / miss / false alarm / correct negative from Table D, with
    optional column filters applied first, e.g.:
        generate_contingency_dict(table_d, Season="2025-26")
        generate_contingency_dict(table_d, Location="Carnarvon")
    Also returns POD (probability of detection) and FAR (false alarm
    ratio) -- see the earlier discussion on why these are NOT the same
    "probability of gales given a warning" question.
    """
    print(f"\n=== Contingency stats (filters={filters or 'none'}) ===")
    df = table_d.copy()

    for key, value in filters.items():
        if key not in df.columns:
            raise ValueError(
                f"Cannot filter on {key!r}: Table D has no such column. "
                f"Available columns: {list(df.columns)}"
            )
        df = df[df[key] == value]
    if filters:
        print(f"[stats] {len(df)} row(s) remain after filtering")

    hit = int((df.Forecast & df.Observed).sum())
    false_alarm = int((df.Forecast & ~df.Observed).sum())
    miss = int((~df.Forecast & df.Observed).sum())
    correct_negative = int((~df.Forecast & ~df.Observed).sum())
    total = hit + false_alarm + miss + correct_negative
    results = {
        "hit": hit,
        "false alarm": false_alarm,
        "miss": miss,
        "correct negative": correct_negative,
        "total": total,
    }
    print(f"[stats] {results}")
    return results


def get_contingency_matrix_df(stats: dict) -> pd.DataFrame:
    """
    Takes the dictionary from build_contingency_table and converts it into
    a formatted 2x2 Contingency Matrix with row/column totals.
    """
    matrix_df = pd.DataFrame(
        data=[
            [stats["hit"], stats["false alarm"], stats["hit"] + stats["false alarm"]],
            [
                stats["miss"],
                stats["correct negative"],
                stats["miss"] + stats["correct negative"],
            ],
            [
                stats["hit"] + stats["miss"],
                stats["false alarm"] + stats["correct negative"],
                stats["total"],
            ],
        ],
        index=pd.MultiIndex.from_tuples(
            [("Forecast", "Yes"), ("Forecast", "No"), ("Forecast", "Total")]
        ),
        columns=pd.MultiIndex.from_tuples(
            [("Observed", "Yes"), ("Observed", "No"), ("Observed", "Total")]
        ),
    )
    return matrix_df


def _output_filename_prefix(
    identifier: str,
    state: str | None = None,
    season: str | None = None,
    base_time_hours: list[int] | None = None,
    generated_date: date | None = None,
    forecast_level: str | None = None,
    x_hours: int | None = None,
    y_hours: int | None = None,
) -> str:
    """Build a readable output prefix containing applied filters and run date."""
    parts = [identifier]
    if season is not None:
        parts.append(f"season-{season}")
    if state is not None:
        parts.append(f"state-{state}")
    if base_time_hours is not None:
        parts.append("base-times-" + "-".join(f"{hour:02d}" for hour in base_time_hours))
    if forecast_level is not None:
        parts.append(f"level-{forecast_level.replace('_', '-')}")
    if x_hours is not None and y_hours is not None:
        parts.append(f"hours-{x_hours}-{y_hours}")
    parts.append(
        f"date-{(generated_date or date.today()).isoformat().replace('-', '')}"
    )
    return "_".join(parts)


def generate_all_tables_for_disturbance(
    disturbance_id: str,
    output_dir: str | Path | None = None,
    x_hours: int = 0,
    y_hours: int = 24,
    forecast_level: str = "watch_warning",
    wind_level: str = "gale",
    coastal_buffer_km: float = DEFAULT_COASTAL_BUFFER_KM,
    relevance_km: float = DEFAULT_RELEVANCE_KM,
    coastal_buffer_cutoff: pd.Timestamp = DEFAULT_COASTAL_BUFFER_CUTOFF,
    state: str | None = None,
    season: str | None = None,
    locations: gpd.GeoDataFrame | None = None,
    forecasts: dict[str, dict] | None = None,
    track: pd.DataFrame | None = None,
    base_time_hours: list[int] | None = None,
) -> dict[str, pd.DataFrame | dict]:
    """Generate Tables A-D for one disturbance, optionally limited by state.

    State filtering is applied to the TC Locations workbook before Table A is
    built, so Tables A-D all contain only locations from the requested state.

    locations / forecasts / track replace the file inputs (towns.xlsx,
    data/geojson, the best-track CSVs) when given; the database-backed
    verification loader supplies all three.
    """
    print(f"##### Generating contingency tables for {disturbance_id} #####")
    if track is None:
        announce_best_track_source()
    all_locations = locations if locations is not None else load_locations()
    if state is not None:
        available_states = sorted(all_locations["state"].dropna().unique().tolist())
        locations_for_table_a = all_locations[
            all_locations["state"] == state
        ].reset_index(drop=True)
        if locations_for_table_a.empty:
            raise ValueError(
                f"State {state!r} was not found in the TC Locations sheet. Available states: {available_states}"
            )
        print(
            f"[state_filter] {len(locations_for_table_a)}/{len(all_locations)} location(s) retained for State={state!r}"
        )
    else:
        locations_for_table_a = all_locations

    if forecasts is not None:
        available_times = sorted(forecasts)
    else:
        available_times = get_reference_times(disturbance_id)
    selected_times = filter_base_times(available_times, base_time_hours)
    selected_forecasts = (
        {time: forecasts[time] for time in selected_times}
        if forecasts is not None
        else None
    )

    table_a = generate_table_a(
        disturbance_id,
        locations_for_table_a,
        coastal_buffer_km=coastal_buffer_km,
        relevance_km=relevance_km,
        coastal_buffer_cutoff=coastal_buffer_cutoff,
        forecasts=selected_forecasts,
        fcast_times=selected_times,
    )

    # Table B/C only need the locations that actually appear in Table A for
    # this disturbance -- not every town in towns.xlsx.
    relevant_names = set(table_a["Location"].unique())
    locations = locations_for_table_a[
        locations_for_table_a["name"].isin(relevant_names)
    ].reset_index(drop=True)
    print(
        f"[relevant_locations] {len(locations)}/{len(locations_for_table_a)} location(s) appear in Table A for {disturbance_id}"
    )

    table_b = generate_table_b(disturbance_id, locations, track=track)
    # Pass the Table B we just built straight in, rather than letting generate_table_c() rebuild it from scratch a second time.
    table_c = generate_table_c(
        disturbance_id,
        locations,
        x_hours=x_hours,
        y_hours=y_hours,
        wind_level=wind_level,
        table_b=table_b,
        fcast_times=selected_times,
    )
    table_d = generate_table_d(table_a, table_c, forecast_level=forecast_level,)
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
        output_prefix = _output_filename_prefix(
            disturbance_id,
            state=state,
            season=season,
            base_time_hours=base_time_hours,
            forecast_level=forecast_level,
            x_hours=x_hours,
            y_hours=y_hours,
        )
        print(f"\n[write] Writing CSVs to {out_dir} ...")
        written: list[Path] = []
        for name, frame in (
            ("table_a", table_a),
            ("table_b", table_b),
            ("table_c", table_c),
            ("table_d", table_d),
            ("contingency_matrix", matrix.reset_index()),
        ):
            out_path = out_dir / f"{output_prefix}_{name}.csv"
            frame.to_csv(out_path, index=False)
            written.append(out_path)
            print(f"[write]   {out_path} ({len(frame)} row(s))")

        summary_path = out_dir / f"{output_prefix}_contingency_summary.csv"
        pd.DataFrame([stats]).to_csv(summary_path, index=False)
        written.append(summary_path)
        outputs["files"] = written
        print(f"[write]   {summary_path}")

    print(f"##### Done: {disturbance_id} #####\n")
    return outputs


def generate_all_tables_for_disturbances(
    disturbance_ids: list[str],
    output_dir: str | Path | None = None,
    x_hours: int = 0,
    y_hours: int = 24,
    forecast_level: str = "watch_warning",
    wind_level: str = "gale",
    coastal_buffer_km: float = DEFAULT_COASTAL_BUFFER_KM,
    relevance_km: float = DEFAULT_RELEVANCE_KM,
    coastal_buffer_cutoff: pd.Timestamp = DEFAULT_COASTAL_BUFFER_CUTOFF,
    state: str | None = None,
    season: str | None = None,
    base_time_hours: list[int] | None = None,
) -> dict[str, object]:
    """Run the full Table A-D pipeline for each disturbance ID in turn (each
    still gets its own per-disturbance CSVs, same as generate_all_tables_for_disturbance),
    then concatenate their Table D's into one combined table so contingency
    stats can be filtered across cyclones by Season rather than being stuck
    within a single disturbance. If state is supplied, it is applied before
    each disturbance's Tables A-D are generated."""
    print(
        f"\n########## Generating combined tables for {len(disturbance_ids)} disturbance(s): {disturbance_ids} ##########"
    )
    per_disturbance = {}
    table_d_frames = []
    for disturbance_id in disturbance_ids:
        outputs = generate_all_tables_for_disturbance(
            disturbance_id,
            output_dir=output_dir,
            x_hours=x_hours,
            y_hours=y_hours,
            forecast_level=forecast_level,
            wind_level=wind_level,
            coastal_buffer_km=coastal_buffer_km,
            relevance_km=relevance_km,
            coastal_buffer_cutoff=coastal_buffer_cutoff,
            state=state,
            season=season,
            base_time_hours=base_time_hours,
        )
        per_disturbance[disturbance_id] = outputs
        table_d_frames.append(outputs["table_d"])

    combined_table_d = (
        pd.concat(table_d_frames, ignore_index=True)
        if table_d_frames
        else pd.DataFrame(
            columns=[
                "Disturbance ID",
                "Base time",
                "Location",
                "Season",
                "Forecast",
                "Observed",
            ]
        )
    )
    print(
        f"\n[combined] Table D across all disturbances: {len(combined_table_d)} row(s)"
    )
    combined_stats = generate_contingency_dict(combined_table_d)
    combined_matrix = get_contingency_matrix_df(combined_stats)
    written_files: list[Path] = []

    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_prefix = _output_filename_prefix(
            "combined",
            state=state,
            season=season,
            base_time_hours=base_time_hours,
            forecast_level=forecast_level,
            x_hours=x_hours,
            y_hours=y_hours,
        )
        combined_table_path = out_dir / f"{output_prefix}_table_d.csv"
        combined_table_d.to_csv(combined_table_path, index=False)
        print(f"[write]   {combined_table_path} ({len(combined_table_d)} row(s))")
        combined_summary_path = out_dir / f"{output_prefix}_contingency_summary.csv"
        pd.DataFrame([combined_stats]).to_csv(combined_summary_path, index=False)
        print(f"[write]   {combined_summary_path}")
        written_files = [
            *(path for outputs in per_disturbance.values() for path in outputs.get("files", [])),
            combined_table_path,
            combined_summary_path,
        ]

    return {
        "per_disturbance": per_disturbance,
        "files": written_files,
        "combined_table_d": combined_table_d,
        "combined_stats": combined_stats,
        "combined_matrix": combined_matrix,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate contingency tables and summary CSVs for one or more cyclone disturbance IDs."
    )
    parser.add_argument(
        "disturbance_id",
        nargs="*",
        help="BOM disturbance ID(s), for example AU202526_34U. Give more than one to combine them into one contingency table. Omit entirely and use --season instead to auto-select every disturbance in a season.",
    )
    parser.add_argument(
        "--season",
        help="Jul-Jun cyclone season, e.g. '2025-26'. If given without any disturbance_id, every disturbance with a forecast base time in that season is found automatically and combined.",
    )
    parser.add_argument(
        "--state",
        help="Limit Tables A-D to locations whose State column in the TC Locations sheet matches this value (e.g. 'WA').",
    )
    parser.add_argument(
        "--output-dir",
        default="data/contingency_tables",
        help="Directory to write the generated CSV tables to",
    )
    parser.add_argument(
        "--x-hours",
        type=int,
        default=0,
        help="Lower bound for observed-gale window in hours from base time (default 0: this is the Warning window's start; use 24 for the Watch window)",
    )
    parser.add_argument(
        "--y-hours",
        type=int,
        default=24,
        help="Upper bound for observed-gale window in hours from base time (default 24: this is the Warning window's end; use 48 for the Watch window). Other windows (e.g. 30, 42) can also be explored.",
    )

    parser.add_argument(
    "--forecast-level",
    choices=["watch", "warning", "watch_warning"],
    default="watch_warning",
)

    parser.add_argument(
        "--wind-level",
        choices=["gale", "storm", "hurricane"],
        default="gale",
    )

    parser.add_argument(
        "--coastal-buffer-km",
        type=float,
        default=DEFAULT_COASTAL_BUFFER_KM,
        help=f"Coastal towns within this many km of a watch/warning polygon edge count as covered (default {DEFAULT_COASTAL_BUFFER_KM}km)",
    )
    parser.add_argument(
        "--coastal-buffer-cutoff",
        default=str(DEFAULT_COASTAL_BUFFER_CUTOFF.date()),
        help=f"Coastal buffer only applies to bulletins before this date (YYYY-MM-DD); threat-area methodology changed after this point (default {DEFAULT_COASTAL_BUFFER_CUTOFF.date()})",
    )
    parser.add_argument(
        "--relevance-km",
        type=float,
        default=DEFAULT_RELEVANCE_KM,
        help=f"Only include towns within this many km of a watch or warning area in Table A (default {DEFAULT_RELEVANCE_KM}km)",
    )
    parser.add_argument(
        "--near-polygon-output",
        nargs="?",
        const="data/near_polygon_distances.csv",
        help="Write the all-cyclone pre-cutoff town-to-watch/warning distance report to this CSV file and exit (default: data/near_polygon_distances.csv)",
    )
    args = parser.parse_args()
    if not args.disturbance_id and not args.season and not args.near_polygon_output:
        parser.error(
            "Provide at least one disturbance_id, or use --season to select a whole season's worth automatically."
        )
    return args


if __name__ == "__main__":
    args = _parse_args()
    try:
        coastal_buffer_cutoff = pd.Timestamp(args.coastal_buffer_cutoff)

        if args.near_polygon_output:
            find_pre_cutoff_near_polygon_distances(
                cutoff=coastal_buffer_cutoff,
                max_distance_km=args.coastal_buffer_km,
                output_csv=args.near_polygon_output,
            )
            raise SystemExit(0)

        if args.season and not args.disturbance_id:
            disturbance_ids = list_disturbance_ids_for_season(args.season)
            if not disturbance_ids:
                raise SystemExit(
                    f"No disturbances found for season {args.season!r}. Has build_gml_dataset.py been run?"
                )
        else:
            disturbance_ids = args.disturbance_id

        # A supplied disturbance ID takes precedence over --season for
        # selection, so only include season in filenames when it actually
        # selected the disturbance set.
        applied_season = (
            args.season if args.season and not args.disturbance_id else None
        )

        if len(disturbance_ids) == 1:
            outputs = generate_all_tables_for_disturbance(
                disturbance_ids[0],
                output_dir=args.output_dir,
                x_hours=args.x_hours,
                y_hours=args.y_hours,
                forecast_level=args.forecast_level,
                wind_level=args.wind_level,
                coastal_buffer_km=args.coastal_buffer_km,
                relevance_km=args.relevance_km,
                coastal_buffer_cutoff=coastal_buffer_cutoff,
                state=args.state,
                season=applied_season,
            )
            table_d, stats = outputs["table_d"], outputs["stats"]
        else:
            outputs = generate_all_tables_for_disturbances(
                disturbance_ids,
                output_dir=args.output_dir,
                x_hours=args.x_hours,
                y_hours=args.y_hours,
                forecast_level=args.forecast_level,
                wind_level=args.wind_level,
                coastal_buffer_km=args.coastal_buffer_km,
                relevance_km=args.relevance_km,
                coastal_buffer_cutoff=coastal_buffer_cutoff,
                state=args.state,
                season=applied_season,
            )
            table_d, stats = outputs["combined_table_d"], outputs["combined_stats"]

        matrix = get_contingency_matrix_df(stats)
        print(f"\nGenerated contingency tables for {disturbance_ids}")
        print(stats)
        print("\nContingency matrix:")
        print(matrix)
    except Exception as exc:  # pragma: no cover - CLI safety path
        raise SystemExit(
            f"Failed to generate contingency tables: {type(exc).__name__}: {exc}"
        ) from exc
