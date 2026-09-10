#!/usr/bin/env python3
"""Build the viz dataset (for visualize.html) AND data/geojson/ (for
gen_cont_tables.py) from the same set of BOM tcData GML bulletins, in one
pass. Reuses gml_to_geojson.py's build_feature_collection() for the GeoJSON
side, so there is only one place that turns GML into geometry -- this script
does not duplicate that logic.

Parses every BOM tcData GML bulletin under data/<REGION>_GMLs/*.gml once and
writes (all under data/ by default -- see --out-dir):

  data/index.json
      { "regions": { "<REGION>": [ {distId, distName, bulletinCount,
                                     firstIssue, lastIssue, hasBestTrack}, ... ] } }

  data/<REGION>/<distId>.json
      A list of bulletin objects (one per source GML file for that cyclone,
      only for cyclones with at least one watch/warning area), shaped as
      before: {distId, distName, source, fcastTime, issueTime, expiryHrs,
      bounds, tracks, fixes, areas}. Unchanged -- visualize.html keeps working.

  data/geojson/<distId>/<sanitized fcastTime>.geojson
      One GeoJSON FeatureCollection per bulletin (every bulletin, not just
      "significant" ones -- gen_cont_tables.py needs the full forecast
      history to build Table A). Shaped as:
      {"type": "FeatureCollection", "metadata": {distId, fcastTime, ...},
       "features": [{"type": "Feature", "properties": {...}, "geometry": {...}}]}
      This is exactly what gen_cont_tables.py's _geojson_index() /
      load_forecast_geojson() already expect -- no changes needed there.

  data/best_track/<distId>.json
      Present only when the BOM "past tropical cyclone tracks" CSV (best
      track / post-event reanalysis) has rows for that distId. Unchanged.

Usage:
    python build_gml_dataset.py
    python build_gml_dataset.py --data-dir data --out-dir data --geojson-out-dir data/geojson
    python build_gml_dataset.py --best-track-csv "data/best_track.csv"
"""

import argparse
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import gml_to_geojson

NAMESPACES = {
    "tc": "http://www.bom.gov.au/dtd/tc",
    "gml": "http://www.opengis.net/gml",
}

AREA_TAGS = ["tcWindArea", "tcForecastArea", "tcWarningArea", "tcWatchArea"]

_INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def text_of(parent, tag):
    el = parent.find(f"tc:{tag}", NAMESPACES)
    return el.text.strip() if el is not None and el.text else None


def parse_coord_list(text):
    if not text:
        return []
    coords = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) != 2:
            continue
        lon, lat = parts
        coords.append([float(lon), float(lat)])
    return coords


def parse_single_coord(text):
    coords = parse_coord_list(text)
    return coords[0] if coords else None


def parse_track(track_el):
    line_string = track_el.find("tc:lineString", NAMESPACES)
    coords_el = (
        line_string.find("gml:coordinates", NAMESPACES)
        if line_string is not None
        else None
    )
    return {
        "coords": parse_coord_list(coords_el.text if coords_el is not None else None),
        "trackType": text_of(track_el, "trackType"),
        "startTime": text_of(track_el, "startTime"),
        "endTime": text_of(track_el, "endTime"),
    }


def parse_fix(fix_el):
    point = fix_el.find("tc:point", NAMESPACES)
    coords_el = point.find("gml:coordinates", NAMESPACES) if point is not None else None
    return {
        "coord": parse_single_coord(coords_el.text if coords_el is not None else None),
        "fixType": text_of(fix_el, "fixType"),
        "fixTime": text_of(fix_el, "fixTime"),
        "symbol": text_of(fix_el, "symbol"),
        "category": text_of(fix_el, "category"),
        "timeOffset": text_of(fix_el, "timeOffset"),
    }


def parse_polygon(polygon_el):
    rings = []
    outer = polygon_el.find(
        "gml:outerBoundaryIs/gml:LinearRing/gml:coordinates", NAMESPACES
    )
    if outer is not None:
        rings.append(parse_coord_list(outer.text))
    for inner in polygon_el.findall(
        "gml:innerBoundaryIs/gml:LinearRing/gml:coordinates", NAMESPACES
    ):
        rings.append(parse_coord_list(inner.text))
    return [r for r in rings if r]


def parse_area(area_el, kind):
    polygons = []
    for polygon_el in area_el.findall(
        "tc:geometry/gml:polygonMember/gml:Polygon", NAMESPACES
    ):
        rings = parse_polygon(polygon_el)
        if rings:
            polygons.append(rings)
    return {
        "kind": kind,
        "polygons": polygons,
        "areaType": text_of(area_el, "areaType"),
        "extent": text_of(area_el, "extent"),
        "windType": text_of(area_el, "windType"),
        "marineType": text_of(area_el, "marineType"),
        "fixType": text_of(area_el, "fixType"),
        "fixTime": text_of(area_el, "fixTime"),
    }


def parse_bounds(root):
    box = root.find("gml:boundedBy/gml:Box", NAMESPACES)
    if box is None:
        return None
    points = []
    for coord in box.findall("gml:coord", NAMESPACES):
        x_el = coord.find("gml:X", NAMESPACES)
        y_el = coord.find("gml:Y", NAMESPACES)
        if x_el is None or y_el is None or x_el.text is None or y_el.text is None:
            continue
        points.append([float(x_el.text), float(y_el.text)])
    return points or None


def parse_bulletin(root, source_name):
    """Build the lightweight viz bulletin shape from an already-parsed
    <root> element (visualize.html's tracks/fixes/areas shape -- unchanged)."""
    tracks = [parse_track(t) for t in root.findall("tc:tcTrack", NAMESPACES)]
    fixes = [parse_fix(f) for f in root.findall("tc:tcFix", NAMESPACES)]
    areas = []
    for kind in AREA_TAGS:
        for area_el in root.findall(f"tc:{kind}", NAMESPACES):
            areas.append(parse_area(area_el, kind))
    return {
        "distId": text_of(root, "distId"),
        "distName": text_of(root, "distName"),
        "source": source_name,
        "fcastTime": text_of(root, "fcastTime"),
        "issueTime": text_of(root, "issueTime"),
        "expiryHrs": text_of(root, "expiryHrs"),
        "bounds": parse_bounds(root),
        "tracks": tracks,
        "fixes": fixes,
        "areas": areas,
    }


def is_significant_bulletin(bulletin):
    if not isinstance(bulletin, dict):
        return False
    return any(
        area.get("kind") in {"tcWarningArea", "tcWatchArea"}
        for area in bulletin.get("areas", [])
    )


def parse_float(text):
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_best_tracks(csv_path):
    if not csv_path or not os.path.isfile(csv_path):
        return {}
    with open(csv_path, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if "DISTURBANCE_ID" in line), None
    )
    if header_idx is None:
        print(
            f"  ! {csv_path}: no DISTURBANCE_ID header found, skipping best track",
            file=sys.stderr,
        )
        return {}
    reader = csv.DictReader(lines[header_idx:])
    by_dist_id = {}
    for row in reader:
        dist_id = (row.get("DISTURBANCE_ID") or "").strip()
        lat = parse_float(row.get("LAT"))
        lon = parse_float(row.get("LON"))
        tm = (row.get("TM") or "").strip()
        if not dist_id or lat is None or lon is None or not tm:
            continue
        point = {
            "time": tm,
            "coord": [lon, lat],
            "pressure": parse_float(row.get("CENTRAL_PRES")),
            "windSpeed": parse_float(row.get("MAX_WIND_SPD")),
        }
        entry = by_dist_id.setdefault(
            dist_id,
            {
                "distId": dist_id,
                "name": (row.get("NAME") or "").strip() or None,
                "points": [],
            },
        )
        entry["points"].append(point)
    for entry in by_dist_id.values():
        entry["points"].sort(key=lambda p: p["time"])
    return by_dist_id


def region_name(dir_name):
    return dir_name.removesuffix("_GMLs")


def sanitize_for_filename(value: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("_", (value or "").strip())
    return cleaned or "unknown"


def write_geojson_bulletin(root, source_name, dist_id, fcast_time, geojson_root):
    """Build the canonical GeoJSON FeatureCollection for one bulletin (via
    gml_to_geojson.build_feature_collection) and write it
    to data/geojson/<distId>/<sanitized fcastTime>.geojson."""
    # gml_to_geojson.build_feature_collection expects "sourceFile" to already
    # be set on root (that's what its own convert_file() does before calling it).
    root.set("sourceFile", source_name)
    feature_collection = gml_to_geojson.build_feature_collection(root)
    dist_dir = os.path.join(geojson_root, sanitize_for_filename(dist_id or "UNKNOWN"))
    os.makedirs(dist_dir, exist_ok=True)
    out_path = os.path.join(
        dist_dir, f"{sanitize_for_filename(fcast_time or source_name)}.geojson"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f)
    return out_path


def build(data_dir, out_dir, geojson_out_dir, best_track_csv=None):
    if not os.path.isdir(data_dir):
        raise SystemExit(f"Error: data directory not found: {data_dir}")

    region_dirs = sorted(
        d
        for d in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, d)) and d.endswith("_GMLs")
    )
    if not region_dirs:
        raise SystemExit(
            f"Error: no region subdirectories found under {data_dir} (expected *_GMLs folders)"
        )

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(geojson_out_dir, exist_ok=True)
    index = {"regions": {}}
    total_files = 0
    total_errors = 0
    total_geojson_written = 0

    best_tracks = load_best_tracks(best_track_csv)
    if best_track_csv:
        if best_tracks:
            print(
                f"Best track CSV: {best_track_csv} -> {len(best_tracks)} disturbances"
            )
        else:
            print(
                f"Best track CSV: {best_track_csv} -> no usable rows found",
                file=sys.stderr,
            )

    for dir_name in region_dirs:
        region = region_name(dir_name)
        region_path = os.path.join(data_dir, dir_name)
        gml_files = sorted(
            f for f in os.listdir(region_path) if f.lower().endswith(".gml")
        )

        by_dist_id = {}
        for fname in gml_files:
            fpath = os.path.join(region_path, fname)
            total_files += 1
            try:
                tree = ET.parse(fpath)
                root = tree.getroot()
            except ET.ParseError as exc:
                print(f"  ! skipping {fpath}: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            bulletin = parse_bulletin(root, fname)
            dist_id = bulletin["distId"] or "UNKNOWN"
            by_dist_id.setdefault(dist_id, []).append(bulletin)

            # Write the canonical GeoJSON for gen_cont_tables.py -- every
            # bulletin, not filtered to "significant" ones, since Table A
            # needs the full forecast history per base time.
            write_geojson_bulletin(
                root, fname, dist_id, bulletin["fcastTime"], geojson_out_dir
            )
            total_geojson_written += 1

        significant_by_dist_id = {
            dist_id: bulletins
            for dist_id, bulletins in by_dist_id.items()
            if any(is_significant_bulletin(b) for b in bulletins)
        }

        region_out_dir = os.path.join(out_dir, region)
        os.makedirs(region_out_dir, exist_ok=True)

        cyclone_entries = []
        for dist_id, bulletins in sorted(significant_by_dist_id.items()):
            bulletins.sort(key=lambda b: b["issueTime"] or "")
            out_path = os.path.join(region_out_dir, f"{dist_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(bulletins, f)

            issue_times = [b["issueTime"] for b in bulletins if b["issueTime"]]
            cyclone_entries.append(
                {
                    "distId": dist_id,
                    "distName": bulletins[-1].get("distName"),
                    "bulletinCount": len(bulletins),
                    "firstIssue": min(issue_times) if issue_times else None,
                    "lastIssue": max(issue_times) if issue_times else None,
                    "hasBestTrack": dist_id in best_tracks,
                }
            )

        cyclone_entries.sort(key=lambda c: c["firstIssue"] or "")
        index["regions"][region] = cyclone_entries
        print(
            f"{region}: {len(gml_files)} files -> {len(cyclone_entries)} significant cyclones"
        )

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    best_track_written = 0
    if best_tracks:
        best_track_out_dir = os.path.join(out_dir, "best_track")
        os.makedirs(best_track_out_dir, exist_ok=True)
        for dist_id, entry in sorted(best_tracks.items()):
            out_path = os.path.join(best_track_out_dir, f"{dist_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(entry, f)
            best_track_written += 1

    print(f"\nParsed {total_files} GML files ({total_errors} errors).")
    print(f"Wrote {out_dir}/index.json and per-cyclone JSON under {out_dir}/<REGION>/.")
    print(
        f"Wrote {total_geojson_written} GeoJSON bulletin file(s) under {geojson_out_dir}/<distId>/."
    )
    if best_track_csv:
        print(
            f"Wrote {best_track_written} best-track file(s) under {out_dir}/best_track/."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Parse BOM tcData GML bulletins into the viz dataset (for visualize.html) "
        "and data/geojson/ (for gen_cont_tables.py) in one pass."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Input directory containing <REGION>_GMLs/ subfolders (default: data)",
    )
    parser.add_argument(
        "--out-dir",
        default="data",
        help="Output directory for index.json and <REGION>/<distId>.json (default: data)",
    )
    parser.add_argument(
        "--geojson-out-dir",
        default="data/geojson",
        help="Output directory for per-bulletin GeoJSON files consumed by gen_cont_tables.py (default: data/geojson)",
    )
    parser.add_argument(
        "--best-track-csv",
        default="data/best_track.csv",
        help="Path to the BOM past-tropical-cyclone-tracks CSV. Pass '' to skip.",
    )
    args = parser.parse_args()
    build(
        args.data_dir,
        args.out_dir,
        args.geojson_out_dir,
        best_track_csv=args.best_track_csv or None,
    )


if __name__ == "__main__":
    main()
