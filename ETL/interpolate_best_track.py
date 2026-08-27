from pathlib import Path

import numpy as np
import pandas as pd


# -------
# Paths
# -------
ETL_DIR = Path(__file__).resolve().parent
INPUT_CSV = ETL_DIR / "Processed" / "best_track_interpolation_input.csv"
OUTPUT_CSV = ETL_DIR / "Processed" / "best_track_interpolated.csv"

STEP_MINUTES = 15


# --------------------------------------
# Fields and wind-radius configuration
# -------------------------------------
LINEAR_COLS = [
    "LAT",
    "LON",
    "MAX_WIND_SPD",
    "POSITION_UNCERTAINTY",
]

# Thresholds in m/s from the tropical-cyclone database specification.
RADIUS_THRESHOLDS = {
    "GF": 17.0,
    "SF": 25.0,
    "HF": 33.0,
}

QUADRANTS = [
    "SECNE",
    "SECSE",
    "SECSW",
    "SECNW",
]

RADIUS_COLS = [
    f"MN_RADIUS_{level}_{quadrant}"
    for level in RADIUS_THRESHOLDS
    for quadrant in QUADRANTS
]


# ----------------------
# Linear interpolation
# -----------------------
def interpolate_linear_fields(
    system: pd.DataFrame,
    step_minutes: int = STEP_MINUTES,
) -> pd.DataFrame:
    """Interpolate track, max wind and position uncertainty to a regular grid."""
    system = system.sort_values("TM").copy()

    start = system["TM"].min().ceil(f"{step_minutes}min")
    end = system["TM"].max().floor(f"{step_minutes}min")
    grid = pd.date_range(start=start, end=end, freq=f"{step_minutes}min")

    # Keep off-grid observations as interpolation anchors, but emit only the
    # standard output grid.
    original_times = pd.DatetimeIndex(system["TM"].drop_duplicates())
    full_index = original_times.union(grid).sort_values()

    indexed = system.set_index("TM")
    reindexed = indexed.reindex(full_index)

    reindexed["IS_INTERPOLATED"] = ~reindexed.index.isin(indexed.index)
    reindexed["DISTURBANCE_ID"] = system["DISTURBANCE_ID"].iloc[0]
    reindexed["NAME"] = system["NAME"].iloc[0]

    for col in LINEAR_COLS:
        reindexed[col] = reindexed[col].interpolate(
            method="time",
            limit_area="inside",
        )

    return (
        reindexed.loc[grid]
        .reset_index()
        .rename(columns={"index": "TM"})
    )


# --------------------------
# Wind-radius interpolation
# ---------------------------
def _interpolate_radius_values(
    original: pd.DataFrame,
    output_times: pd.DatetimeIndex,
    output_winds: np.ndarray,
    original_positions: np.ndarray,
    left_positions: np.ndarray,
    right_positions: np.ndarray,
    choose_left: np.ndarray,
    radius_col: str,
    threshold: float,
) -> np.ndarray:
    """Return one interpolated quadrant-radius column"""
    values = np.full(len(output_times), np.nan, dtype=float)

    original_winds = original["MAX_WIND_SPD"].to_numpy(dtype=float)
    original_radii = original[radius_col].to_numpy(dtype=float)
    original_ns = original.index.asi8
    output_ns = output_times.asi8

    for i, wind in enumerate(output_winds):
        original_pos = original_positions[i]

        # Preserve original observations exactly, including 0 and NaN.
        if original_pos >= 0:
            values[i] = original_radii[original_pos]
            continue

        if pd.isna(wind):
            continue

        left_pos = left_positions[i]
        right_pos = right_positions[i]

        # The regular grid is built inside the source time range, so this is
        # only a defensive boundary check.
        if left_pos < 0 or right_pos >= len(original):
            continue

        radius_left = original_radii[left_pos]
        radius_right = original_radii[right_pos]
        wind_left = original_winds[left_pos]
        wind_right = original_winds[right_pos]

        left_missing = pd.isna(radius_left)
        right_missing = pd.isna(radius_right)

        left_zero = pd.notna(radius_left) and radius_left == 0
        right_zero = pd.notna(radius_right) and radius_right == 0

        left_has_radius = pd.notna(radius_left) and radius_left != 0
        right_has_radius = pd.notna(radius_right) and radius_right != 0

        # Case 1: both radii are known -> linear interpolation.
        if left_has_radius and right_has_radius:
            fraction = (
                (output_ns[i] - original_ns[left_pos])
                / (original_ns[right_pos] - original_ns[left_pos])
            )
            values[i] = radius_left + fraction * (radius_right - radius_left)
            continue

        # Explicit no-radius (0) <-> actual radius:
        # use the nearest original observation; earlier wins an exact midpoint.
        if (
            (left_has_radius and right_zero)
            or (left_zero and right_has_radius)
        ):
            values[i] = radius_left if choose_left[i] else radius_right
            continue

        # Both radii are unknown.
        if left_missing and right_missing:
            continue

        # 0 means known absence, while NaN means unknown. 
        # The supplied client examples do not define interpolation between these states, so leave interior values unknown.
        if (
            (left_zero and right_missing)
            or (left_missing and right_zero)
        ):
            continue

        # The remaining cases require endpoint wind speeds.
        if pd.isna(wind_left) or pd.isna(wind_right):
            continue

        left_above = wind_left >= threshold
        right_above = wind_right >= threshold

        # Case 2: one radius is known and wind crosses the threshold.
        # Use the known radius only while interpolated wind is at/above it.
        if left_above != right_above:
            if left_has_radius and left_above:
                known_radius = radius_left
            elif right_has_radius and right_above:
                known_radius = radius_right
            else:
                continue

            if wind >= threshold:
                values[i] = known_radius
            continue

        # Case 3: both endpoint winds are above threshold but only one radius
        # is known. Use the closest original observation; earlier wins ties.
        if left_above and right_above:
            if choose_left[i]:
                if left_has_radius:
                    values[i] = radius_left
            else:
                if right_has_radius:
                    values[i] = radius_right

    return values


def interpolate_wind_radii(
    original_system: pd.DataFrame,
    interpolated_system: pd.DataFrame,
) -> pd.DataFrame:
    """Interpolate all GF/SF/HF quadrant radii."""
    original = original_system.sort_values("TM").set_index("TM")
    result = interpolated_system.copy()

    output_times = pd.DatetimeIndex(result["TM"])
    original_times = original.index

    # These positions and midpoint decisions are identical for all 12 radius
    # columns, so calculate them only once per cyclone.
    original_positions = original_times.get_indexer(output_times)
    right_positions = original_times.searchsorted(output_times, side="right")
    left_positions = right_positions - 1

    choose_left = np.zeros(len(output_times), dtype=bool)
    valid = (
        (original_positions < 0)
        & (left_positions >= 0)
        & (right_positions < len(original_times))
    )

    if valid.any():
        output_ns = output_times.asi8
        original_ns = original_times.asi8

        left_distance = (
            output_ns[valid]
            - original_ns[left_positions[valid]]
        )
        right_distance = (
            original_ns[right_positions[valid]]
            - output_ns[valid]
        )

        choose_left[valid] = left_distance <= right_distance

    output_winds = result["MAX_WIND_SPD"].to_numpy(dtype=float)

    for level, threshold in RADIUS_THRESHOLDS.items():
        for quadrant in QUADRANTS:
            radius_col = f"MN_RADIUS_{level}_{quadrant}"

            result[radius_col] = _interpolate_radius_values(
                original=original,
                output_times=output_times,
                output_winds=output_winds,
                original_positions=original_positions,
                left_positions=left_positions,
                right_positions=right_positions,
                choose_left=choose_left,
                radius_col=radius_col,
                threshold=threshold,
            )

    return result


# ------------------------------
# Full best-track interpolation
# -------------------------------
def interpolate_system(
    system: pd.DataFrame,
    step_minutes: int = STEP_MINUTES,
) -> pd.DataFrame:
    interpolated = interpolate_linear_fields(
        system,
        step_minutes=step_minutes,
    )

    return interpolate_wind_radii(
        system,
        interpolated,
    )


def interpolate_best_track(
    best_track: pd.DataFrame,
    step_minutes: int = STEP_MINUTES,
) -> pd.DataFrame:
    interpolated_systems = [
        interpolate_system(
            system,
            step_minutes=step_minutes,
        )
        for _, system in best_track.groupby(
            "DISTURBANCE_ID",
            sort=False,
        )
    ]

    return pd.concat(
        interpolated_systems,
        ignore_index=True,
    )



def main() -> None:
    best_track = pd.read_csv(
        INPUT_CSV,
        parse_dates=["TM"],
    )

    best_track_interpolated = interpolate_best_track(
        best_track
    )

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    best_track_interpolated.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    print("Input rows:", len(best_track))
    print(
        "Systems:",
        best_track["DISTURBANCE_ID"].nunique(),
    )
    print(
        "Interpolated rows:",
        len(best_track_interpolated),
    )
    print("Saved:", OUTPUT_CSV)


if __name__ == "__main__":
    main()
