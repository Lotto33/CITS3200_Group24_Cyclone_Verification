import tempfile
import zipfile
from pathlib import Path

from app.build_gml_dataset import build
from app.db.session import SessionLocal
from app.models.enums import IngestKind, TrackDataset
from app.services.interpolation.interpolation_pipeline import run_interpolation_pipeline
from app.services.loaders.best_track import load_best_track, read_best_track_csv
from app.services.loaders.common import Stats, ingest_run
from app.services.loaders.gml import load_bulletins
from app.services.loaders.interpolation import load_interpolation


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
            f"No region GML directories found in {input_dir}; expected folders "
            "such as WA_GMLs"
        )
    # NOTE: This validates that the uploaded region directories contain GML files.
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
        if region_dir.is_dir()
        and region_dir.name
        in {path.name.removesuffix("_GMLs") for path in region_dirs}
        for path in region_dir.glob("*.json")
        if path.is_file()
    )

    index_path = data_dir / "index.json"
    if not index_path.is_file():
        raise RuntimeError(
            f"Parser completed without generating expected index: {index_path}"
        )
    if generated_geojson_count == 0:
        raise RuntimeError(
            f"Parser completed without generating GeoJSON files under {geojson_dir}"
        )

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


def process_uploaded_gml_archive(archive_path: Path, data_dir: Path) -> dict:
    """Extract a GML ZIP and immediately run the existing parser."""
    archive_path = Path(archive_path).resolve()
    if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
        raise ValueError("Expected a .zip archive containing *_GMLs directories")

    with tempfile.TemporaryDirectory(prefix="cyclone-gml-") as temp_dir:
        staging_dir = Path(temp_dir)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (staging_dir / member.filename).resolve()
                if target != staging_dir and staging_dir not in target.parents:
                    raise ValueError("ZIP contains an unsafe path")
            archive.extractall(staging_dir)

        # Allow archives with a single top-level folder around the region dirs.
        input_dir = staging_dir
        children = list(staging_dir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            input_dir = children[0]
        print("=== Database ingest: GML bulletins ===")
        with SessionLocal() as session:
            stats = Stats()
            with ingest_run(
                session,
                IngestKind.GML,
                source=f"uploaded:{archive_path.name}",
            ) as run:
                counts = load_bulletins(
                    session,
                    data_dir=input_dir,
                    ingest_run_id=run.id,
                    stats=stats,
                )
                run.rows_read = counts["rows_read"]
                run.rows_written = counts["rows_written"]
                run.rows_skipped = counts["rows_skipped"]
                run.stats = stats.as_dict()
            session.commit()
        print(
            f"Database GML ingest: {counts['rows_read']} files read, "
            f"{counts['rows_written']} written, {counts['rows_skipped']} unchanged"
        )
        print("=== Static viewer dataset generation ===")
        return process_gml_dataset(input_dir, data_dir)


def interpolate_and_process_dataset(data_dir: Path) -> dict:
    """Interpolate best track, then rebuild JSON/GeoJSON outputs from it."""
    run_interpolation_pipeline()
    return process_gml_dataset(Path(data_dir) / "gml", data_dir)


def process_uploaded_best_track(csv_path: Path, data_dir: Path) -> dict:
    """Store a best-track upload in the DB and create DB interpolation points."""
    csv_path = Path(csv_path).resolve()
    data_dir = Path(data_dir).resolve()
    if not csv_path.is_file() or csv_path.suffix.lower() != ".csv":
        raise ValueError("Expected a best-track .csv file")

    raw_target = data_dir / "best_track.csv"
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    raw_target.write_bytes(csv_path.read_bytes())

    print("=== Database ingest: best-track observations ===")
    with SessionLocal() as session:
        stats = Stats()
        frame = read_best_track_csv(raw_target)
        with ingest_run(
            session,
            IngestKind.BEST_TRACK,
            source=str(raw_target),
        ) as run:
            counts = load_best_track(
                session,
                frame,
                dataset=TrackDataset.BOM_BEST_TRACK,
                ingest_run_id=run.id,
                stats=stats,
            )
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()
        session.commit()
        print(
            f"Database best-track ingest: {counts['rows_read']} rows read, "
            f"{counts['rows_written']} observations written"
        )

        interpolation: dict[str, int] | None = None
        interpolation_error: str | None = None
        try:
            print("=== Database interpolation ===")
            interpolation_stats = Stats()
            with ingest_run(
                session,
                IngestKind.INTERPOLATION,
                source="uploaded best-track observations",
            ) as run:
                interpolation = load_interpolation(
                    session,
                    dataset=TrackDataset.BOM_BEST_TRACK,
                    label="uploaded best-track",
                    replace=True,
                    stats=interpolation_stats,
                )
                run.rows_read = interpolation["rows_read"]
                run.rows_written = interpolation["rows_written"]
                run.stats = interpolation_stats.as_dict()
            session.commit()
            print(
                "Database interpolation: "
                f"{interpolation['rows_written']} points written"
            )
        except ValueError as exc:
            # The raw best-track ingest is useful even when no watch/warning
            # bulletins exist yet to constrain interpolation.
            session.rollback()
            interpolation_error = str(exc)
            print(f"Database interpolation skipped: {interpolation_error}")

    return {
        "status": "success",
        "best_track_csv": str(raw_target),
        "rows_read": counts["rows_read"],
        "rows_written": counts["rows_written"],
        "interpolation": interpolation,
        "interpolation_error": interpolation_error,
    }