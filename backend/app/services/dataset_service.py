from pathlib import Path

from app.build_gml_dataset import build


def process_gml_dataset(input_dir: Path):
    # 1. Validate input
    # 2. Prepare uploaded/staging directories
    # 3. Call existing converter
    # 4. Check generated outputs
    # 5. Return result

    build(
        data_dir=input_dir,
        out_dir=...,
        geojson_out_dir=...,
        best_track_csv=...
    )

    return {
        "status": "success"
    }