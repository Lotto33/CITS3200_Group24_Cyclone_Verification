from pathlib import Path

import pandas as pd


# -------
# Paths
# -------
ETL_DIR = Path(__file__).resolve().parent

RAW_BEST_TRACK_CSV = ETL_DIR / "Raw" / "IDCKMSTM0S.csv"
RELEVANT_IDS_CSV = ETL_DIR / "Processed" / "relevant_disturbance_ids.csv"

RELEVANT_BEST_TRACK_CSV = ETL_DIR / "Processed" / "relevant_best_track_raw.csv"
INTERPOLATION_INPUT_CSV = ETL_DIR / "Processed" / "best_track_interpolation_input.csv"

PROJECT_START = pd.Timestamp("2016-07-01", tz="UTC")


# Columns required by the current best-track interpolation specification
INTERPOLATION_COLUMNS = [
    # Identification
    "NAME",
    "DISTURBANCE_ID",
    "TM",

    # Position and intensity
    "LAT",
    "LON",
    "POSITION_UNCERTAINTY",
    "MAX_WIND_SPD",

    # Gale-force wind radii
    "MN_RADIUS_GF_SECNE",
    "MN_RADIUS_GF_SECSE",
    "MN_RADIUS_GF_SECSW",
    "MN_RADIUS_GF_SECNW",

    # Storm-force wind radii
    "MN_RADIUS_SF_SECNE",
    "MN_RADIUS_SF_SECSE",
    "MN_RADIUS_SF_SECSW",
    "MN_RADIUS_SF_SECNW",

    # Hurricane-force wind radii
    "MN_RADIUS_HF_SECNE",
    "MN_RADIUS_HF_SECSE",
    "MN_RADIUS_HF_SECSW",
    "MN_RADIUS_HF_SECNW",
]

NUMERIC_COLUMNS = [
    "LAT",
    "LON",
    "POSITION_UNCERTAINTY",
    "MAX_WIND_SPD",

    "MN_RADIUS_GF_SECNE",
    "MN_RADIUS_GF_SECSE",
    "MN_RADIUS_GF_SECSW",
    "MN_RADIUS_GF_SECNW",

    "MN_RADIUS_SF_SECNE",
    "MN_RADIUS_SF_SECSE",
    "MN_RADIUS_SF_SECSW",
    "MN_RADIUS_SF_SECNW",

    "MN_RADIUS_HF_SECNE",
    "MN_RADIUS_HF_SECSE",
    "MN_RADIUS_HF_SECSW",
    "MN_RADIUS_HF_SECNW",
]


# ----------------------------
# 1. Load raw best-track data
# ----------------------------
def load_raw_best_track() -> pd.DataFrame:
    # The first 4 rows of the BoM CSV are metadata
    # row 5 is the header.
    raw = pd.read_csv(
        RAW_BEST_TRACK_CSV,
        skiprows=4,
        low_memory=False,
    )
    return raw


# ----------------------------
# 2. Filter to 2016/17 onwards
# ----------------------------
def filter_project_period(raw: pd.DataFrame) -> pd.DataFrame:
    best_track = raw.copy()

    # The metadata states that TM is UTC.
    best_track["TM"] = pd.to_datetime(best_track["TM"], utc=True)

    best_track_2016_onwards = best_track[
        best_track["TM"] >= PROJECT_START
    ].copy()

    print("\n--- Project-period filter ---")
    print("Raw rows:", len(raw))
    print("Remaining rows:", len(best_track_2016_onwards))
    print("Rows discarded:", len(raw) - len(best_track_2016_onwards))
    print("Earliest remaining TM:", best_track_2016_onwards["TM"].min())
    print("Latest remaining TM:", best_track_2016_onwards["TM"].max())

    return best_track_2016_onwards


# ---------------------------------------------------------------------
# 3. Load disturbance IDs identified from Watch/Warning GML products
# ---------------------------------------------------------------------
def load_relevant_ids() -> tuple[pd.DataFrame, set[str]]:
    relevant_disturbances = pd.read_csv(RELEVANT_IDS_CSV)

    relevant_ids = set(
        relevant_disturbances["DISTURBANCE_ID"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    print("\n--- Relevant GML disturbances ---")
    print("Relevant disturbance IDs:", len(relevant_ids))

    return relevant_disturbances, relevant_ids


# ------------------------------------
# 4. Keep matching best-track systems
# ------------------------------------
def filter_relevant_systems(
    best_track_2016_onwards: pd.DataFrame,
    relevant_ids: set[str],
) -> tuple[pd.DataFrame, set[str]]:   
    # Standardise ID whitespace before matching.
    best_track_2016_onwards = best_track_2016_onwards.copy()
    best_track_2016_onwards["DISTURBANCE_ID"] = (
        best_track_2016_onwards["DISTURBANCE_ID"]
        .astype(str)
        .str.strip()
    )

    best_track_relevant = best_track_2016_onwards[
        best_track_2016_onwards["DISTURBANCE_ID"].isin(relevant_ids)
    ].copy()

    csv_ids = set(best_track_2016_onwards["DISTURBANCE_ID"])
    missing_ids = relevant_ids - csv_ids

    print("\n--- Relevant best-track filter ---")
    print("Before filtering:", best_track_2016_onwards.shape)
    print("After filtering:", best_track_relevant.shape)
    print(
        "Matched unique disturbance IDs:",
        best_track_relevant["DISTURBANCE_ID"].nunique(),
    )
    print("Relevant GML IDs not found in best-track CSV:", sorted(missing_ids))

    return best_track_relevant, missing_ids


# ------------------------------
# 5. Create interpolation input
# -------------------------------
def prepare_interpolation_input(
    best_track_relevant: pd.DataFrame,
) -> pd.DataFrame:
    best_track_interpolation_input = (
        best_track_relevant[INTERPOLATION_COLUMNS]
        .copy()
        .sort_values(["DISTURBANCE_ID", "TM"])
        .reset_index(drop=True)
    )

    # Before numeric conversion, record the distinction between blank values
    # and explicit zeros in the source data.
    blank_counts = best_track_interpolation_input.apply(
        lambda col: col.map(
            lambda x: isinstance(x, str) and x.strip() == ""
        ).sum()
    )

    zero_counts = best_track_interpolation_input.apply(
        lambda col: (pd.to_numeric(col, errors="coerce") == 0).sum()
    )

    print("\n--- Blank values before numeric conversion ---")
    print(blank_counts)

    print("\n--- Explicit zero values before numeric conversion ---")
    print(zero_counts)

    # Convert measurement fields to numeric.
    # Blank/non-numeric values become NaN; explicit zero stays 0.
    best_track_interpolation_input[NUMERIC_COLUMNS] = (
        best_track_interpolation_input[NUMERIC_COLUMNS]
        .apply(pd.to_numeric, errors="coerce")
    )

    return best_track_interpolation_input


# --------------------------------------------------------
# 6. Data-quality checks used during notebook exploration
# --------------------------------------------------------
def print_data_quality_summary(
    best_track_interpolation_input: pd.DataFrame,
) -> None:
    print("\n--- Missing values after numeric conversion ---")
    print(best_track_interpolation_input.isna().sum())

    duplicates = best_track_interpolation_input[
        best_track_interpolation_input.duplicated(
            subset=["DISTURBANCE_ID", "TM"],
            keep=False,
        )
    ].sort_values(["DISTURBANCE_ID", "TM"])

    print("\n--- Duplicate DISTURBANCE_ID + TM rows ---")
    print("Number of duplicate rows:", len(duplicates))
    if not duplicates.empty:
        print(duplicates[["DISTURBANCE_ID", "TM"]])

    time_gaps = (
        best_track_interpolation_input
        .groupby("DISTURBANCE_ID")["TM"]
        .diff()
    )

    print("\n--- Observation time gaps ---")
    print(time_gaps.value_counts().sort_index())

    missing_linear = best_track_interpolation_input[
        best_track_interpolation_input[
            ["POSITION_UNCERTAINTY", "MAX_WIND_SPD"]
        ].isna().any(axis=1)
    ][
        [
            "DISTURBANCE_ID",
            "TM",
            "LAT",
            "LON",
            "POSITION_UNCERTAINTY",
            "MAX_WIND_SPD",
        ]
    ]

    print("\n--- Rows missing POSITION_UNCERTAINTY or MAX_WIND_SPD ---")
    if missing_linear.empty:
        print("None")
    else:
        print(missing_linear.to_string(index=False))
        print("\nAffected systems:")
        print(missing_linear["DISTURBANCE_ID"].value_counts())


# -------------------------
# 7. Export processed data
# -------------------------
def export_processed_data(
    best_track_relevant: pd.DataFrame,
    best_track_interpolation_input: pd.DataFrame,
) -> None:
    RELEVANT_BEST_TRACK_CSV.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- Output ---")
    # Full relevant best-track rows are retained for traceability
    # any downstream fields that may be needed later.
    best_track_relevant.to_csv(
        RELEVANT_BEST_TRACK_CSV,
        index=False,
    )
    print("Saved:", RELEVANT_BEST_TRACK_CSV)

    # Clean, numeric input used by the interpolation stage.
    best_track_interpolation_input.to_csv(
        INTERPOLATION_INPUT_CSV,
        index=False,
    )
    print("Saved:", INTERPOLATION_INPUT_CSV)


def main() -> None:
    raw = load_raw_best_track()

    best_track_2016_onwards = filter_project_period(raw)

    _, relevant_ids = load_relevant_ids()

    best_track_relevant, _ = filter_relevant_systems(
        best_track_2016_onwards,
        relevant_ids,
    )

    best_track_interpolation_input = prepare_interpolation_input(
        best_track_relevant
    )

    print_data_quality_summary(best_track_interpolation_input)

    export_processed_data(
        best_track_relevant,
        best_track_interpolation_input,
    )


if __name__ == "__main__":
    main()