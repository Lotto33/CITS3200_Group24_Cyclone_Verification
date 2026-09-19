from pathlib import Path

from app.build_gml_dataset import build


def process_gml_dataset(input_dir: Path, data_dir: Path) -> dict:
    """Parse GML bulletins and return a summary of generated datasets.

    ``input_dir`` must contain region folders such as ``WA_GMLs`` and
    ``data_dir`` is the persistent output/data directory. The processed
    interpolated best-track CSV is preferred when it exists; otherwise the
    raw best-track CSV is passed to the parser.
    """
    input_dir = Path(input_dir).resolve()
    data_dir = Path(data_dir).resolve()

    if not input_dir.is_dir():
        raise FileNotFoundError(f"GML input directory not found: {input_dir}")

    region_dirs = sorted(
        path for path in input_dir.iterdir()
        if path.is_dir() and path.name.endswith("_GMLs")
    )
    if not region_dirs:
        raise ValueError(
            f"No region GML directories found in {input_dir}; expected folders such as WA_GMLs"
        )
    #NOTE : FOR DEBUGGING This counts the number of .gml files in the region directories. If there are no .gml files, it raises a ValueError.
    gml_file_count = sum(
        1 for region_dir in region_dirs
        for path in region_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".gml"
    )
    if gml_file_count == 0:
        raise ValueError(f"No .gml files found in region directories under {input_dir}")

    # Prepare the persistent output locations before invoking the existing
    # parser. build() creates some of these itself, but doing it here keeps
    # the service's filesystem contract explicit and makes output validation
    # predictable.
    data_dir.mkdir(parents=True, exist_ok=True)
    geojson_dir = data_dir / "geojson"
    geojson_dir.mkdir(parents=True, exist_ok=True)

    interpolated_csv = data_dir / "processed" / "best_track_interpolated.csv"
    raw_csv = data_dir / "best_track.csv"
    best_track_csv = interpolated_csv if interpolated_csv.is_file() else raw_csv
    best_track_source = "interpolated" if best_track_csv == interpolated_csv else "raw"

    build(
        data_dir=input_dir,
        out_dir=data_dir,
        geojson_out_dir=geojson_dir,
        best_track_csv=best_track_csv if best_track_csv.is_file() else None,
    )

    generated_geojson_count = sum(
        1 for path in geojson_dir.rglob("*.geojson") if path.is_file()
    )
    generated_region_json_count = sum(
        1 for region_dir in data_dir.iterdir()
        if region_dir.is_dir() and region_dir.name in {path.name.removesuffix("_GMLs") for path in region_dirs}
        for path in region_dir.glob("*.json")
        if path.is_file()
    )

    index_path = data_dir / "index.json"
    if not index_path.is_file():
        raise RuntimeError(f"Parser completed without generating expected index: {index_path}")
    if generated_geojson_count == 0:
        raise RuntimeError(f"Parser completed without generating GeoJSON files under {geojson_dir}")

    return {
        "status": "success",
        "input_dir": str(input_dir),
        "output_dir": str(data_dir),
        "best_track_source": best_track_source,
        "best_track_csv": str(best_track_csv) if best_track_csv.is_file() else None,
        "region_count": len(region_dirs),
        "gml_file_count": gml_file_count,
        "geojson_file_count": generated_geojson_count,
        "regional_json_file_count": generated_region_json_count,
        "index_path": str(index_path),
    }


def get_status(data_dir: Path) -> dict:
    """Return the current generated-dataset status without running the parser."""
    data_dir = Path(data_dir).resolve()
    index_path = data_dir / "index.json"
    geojson_dir = data_dir / "geojson"
    geojson_count = sum(
        1 for path in geojson_dir.rglob("*.geojson") if path.is_file()
    ) if geojson_dir.is_dir() else 0

    return {
        "status": "ready" if index_path.is_file() and geojson_count else "not_ready",
        "data_dir": str(data_dir),
        "index_exists": index_path.is_file(),
        "geojson_exists": geojson_dir.is_dir(),
        "geojson_file_count": geojson_count,
    }