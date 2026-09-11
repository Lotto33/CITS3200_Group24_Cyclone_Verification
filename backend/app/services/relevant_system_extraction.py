from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd


# -------
# Paths
# ------
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
GML_ROOT = DATA_DIR / "gml"
PROCESSED_DIR = DATA_DIR / "processed"

OUTPUT_RELEVANT_IDS = PROCESSED_DIR / "relevant_disturbance_ids.csv"

# ---------------------
# 1. Find all GML files
# ----------------------
def find_gml_files() -> list[Path]:
    gml_files = list(GML_ROOT.rglob("*.gml"))

    print("--- GML files ---")
    print("Total GML files:", len(gml_files))

    return gml_files


# --------------------------------------------
# 2. Extract disturbance ID and areaType Info from a file
# --------------------------------------------
def extract_gml_info(file_path: Path):
    tree = ET.parse(file_path)
    root = tree.getroot()

    disturbance_id = None
    advice = set()

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]

        if tag == "distId" and elem.text:
            disturbance_id = elem.text.strip()

        elif tag == "areaType" and elem.text:
            area_type = elem.text.strip()

            if area_type == "Watch Area":
                advice.add("watch")
            elif area_type == "Warning Area":
                advice.add("warning")

    return disturbance_id, advice


# ----------------------------------------------------------------------------
# 3. Process all GML files and map disturbance IDs to files and advice types
# ---------------------------------------------------------------------------
def process_gml_files(gml_files):
    disturbance_files = defaultdict(list)
    disturbance_advice = defaultdict(set)
    unmatched_files = []

    for file_path in gml_files:
        disturbance_id, advice = extract_gml_info(file_path)

        if disturbance_id is None:
            unmatched_files.append(file_path)
            continue

        disturbance_files[disturbance_id].append(file_path)
        disturbance_advice[disturbance_id].update(advice)

    mapped_file_count = sum(
        len(files)
        for files in disturbance_files.values()
    )

    all_mapped_files = [
        file_path
        for files in disturbance_files.values()
        for file_path in files
    ]

    duplicate_mapped_files = (
        len(all_mapped_files)
        - len(set(all_mapped_files))
    )

    relevant_count = sum(
        bool(advice)
        for advice in disturbance_advice.values()
    )

    print("\n--- Disturbance-file mapping ---")
    print("Unique disturbance IDs:", len(disturbance_files))
    print("Mapped files:", mapped_file_count)
    print("Unmatched files:", len(unmatched_files))
    print("Duplicate mapped files:", duplicate_mapped_files)

    print("\n--- Watch/Warning filtering ---")
    print("Total disturbance IDs:", len(disturbance_advice))
    print("Watch/Warning disturbance IDs:", relevant_count)

    return (
        dict(disturbance_files),
        dict(disturbance_advice),
        unmatched_files
    )


# ----------------------------------------------
# 4. Build and export relevant disturbance table
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

#-------------------------------------
# 5. Export relevant disturbance table
#-------------------------------------

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

    disturbance_files, disturbance_advice, unmatched_files = process_gml_files(
        gml_files
    )
    

    relevant_disturbances = build_relevant_disturbances(
        disturbance_advice
    )

    export_relevant_disturbances(
        relevant_disturbances
    )


if __name__ == "__main__":
    main()