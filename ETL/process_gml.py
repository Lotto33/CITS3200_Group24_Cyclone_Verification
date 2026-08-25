from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd


# -------
# Paths
# ------
ETL_DIR = Path(__file__).resolve().parent

GML_ROOT = ETL_DIR / "Raw" / "GML"
OUTPUT_RELEVANT_IDS = ETL_DIR / "Processed" / "relevant_disturbance_ids.csv"


# ---------------------
# 1. Find all GML files
# ----------------------
def find_gml_files() -> list[Path]:
    gml_files = list(GML_ROOT.rglob("*.gml"))

    print("--- GML files ---")
    print("Total GML files:", len(gml_files))

    return gml_files


# --------------------------------------------
# 2. Extract disturbance ID from one GML file
# --------------------------------------------
def extract_disturbance_id(file_path: Path) -> str | None:
    tree = ET.parse(file_path)
    root = tree.getroot()

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]

        if tag == "distId" and elem.text:
            return elem.text.strip()

    return None


# --------------------------------------------------
# 3. Map disturbance IDs to all associated GML files
# --------------------------------------------------
def map_disturbance_files(
    gml_files: list[Path],
) -> tuple[dict[str, list[Path]], list[Path]]:
    disturbance_files = defaultdict(list)
    unmatched_files = []

    for file_path in gml_files:
        disturbance_id = extract_disturbance_id(file_path)

        if disturbance_id is None:
            unmatched_files.append(file_path)
        else:
            disturbance_files[disturbance_id].append(file_path)

    mapped_file_count = sum(
        len(files) for files in disturbance_files.values()
    )

    all_mapped_files = [
        file_path
        for files in disturbance_files.values()
        for file_path in files
    ]

    duplicate_mapped_files = (
        len(all_mapped_files) - len(set(all_mapped_files))
    )

    print("\n--- Disturbance-file mapping ---")
    print("Unique disturbance IDs:", len(disturbance_files))
    print("Mapped files:", mapped_file_count)
    print("Unmatched files:", len(unmatched_files))
    print("Duplicate mapped files:", duplicate_mapped_files)

    return dict(disturbance_files), unmatched_files


# ---------------------------------------------
# 4. Detect Watch/Warning areas in one GML file
# ----------------------------------------------
def get_watch_warning(file_path: Path) -> set[str]:
    tree = ET.parse(file_path)
    root = tree.getroot()

    advice_types = set()

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]

        if tag == "areaType" and elem.text:
            area_type = elem.text.strip()

            if area_type == "Watch Area":
                advice_types.add("watch")
            elif area_type == "Warning Area":
                advice_types.add("warning")

    return advice_types


# -----------------------------------------------------------
# 5. Combine advice types across all files for each disturbance
# ------------------------------------------------------------
def get_disturbance_advice(
    disturbance_files: dict[str, list[Path]],
) -> dict[str, set[str]]:
    disturbance_advice = {}

    for disturbance_id, files in disturbance_files.items():
        advice = set()

        for file_path in files:
            advice.update(get_watch_warning(file_path))

        disturbance_advice[disturbance_id] = advice

    relevant_count = sum(
        bool(advice)
        for advice in disturbance_advice.values()
    )

    print("\n--- Watch/Warning filtering ---")
    print("Total disturbance IDs:", len(disturbance_advice))
    print("Watch/Warning disturbance IDs:", relevant_count)

    return disturbance_advice


# ----------------------------------------------
# 6. Build and export relevant disturbance table
# ----------------------------------------------
def build_relevant_disturbances(
    disturbance_advice: dict[str, set[str]],
) -> pd.DataFrame:
    relevant_disturbances = pd.DataFrame([
        {
            "DISTURBANCE_ID": disturbance_id,
            "WATCH": "watch" in advice,
            "WARNING": "warning" in advice,
        }
        for disturbance_id, advice in disturbance_advice.items()
        if advice
    ])

    relevant_disturbances = (
        relevant_disturbances
        .sort_values("DISTURBANCE_ID")
        .reset_index(drop=True)
    )

    return relevant_disturbances


def export_relevant_disturbances(
    relevant_disturbances: pd.DataFrame,
) -> None:
    OUTPUT_RELEVANT_IDS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    relevant_disturbances.to_csv(
        OUTPUT_RELEVANT_IDS,
        index=False,
    )

    print("\n--- Output ---")
    print("Rows:", len(relevant_disturbances))
    print("Saved:", OUTPUT_RELEVANT_IDS)


def main() -> None:
    gml_files = find_gml_files()

    disturbance_files, _ = map_disturbance_files(gml_files)

    disturbance_advice = get_disturbance_advice(
        disturbance_files
    )

    relevant_disturbances = build_relevant_disturbances(
        disturbance_advice
    )

    export_relevant_disturbances(
        relevant_disturbances
    )


if __name__ == "__main__":
    main()