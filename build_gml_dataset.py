#!/usr/bin/env python3
"""Build the viz_data/ dataset consumed by visualize.html (and visualize_ol.html).

Parses every BOM tcData GML bulletin under data/<REGION>_GMLs/*.gml once and
writes:

  viz_data/index.json
      { "regions": { "<REGION>": [ {distId, distName, bulletinCount,
                                     firstIssue, lastIssue}, ... ] } }

  viz_data/<REGION>/<distId>.json
      A list of bulletin objects (one per source GML file for that cyclone),
      sorted by issue time, each shaped as:

      {
        "distId": str, "distName": str, "source": str (source filename),
        "fcastTime": str, "issueTime": str, "expiryHrs": str,
        "bounds": [[minLon, minLat], [maxLon, maxLat]] | null,
        "tracks": [ {"coords": [[lon, lat], ...], "trackType": str,
                     "startTime": str, "endTime": str}, ... ],
        "fixes":  [ {"coord": [lon, lat], "fixType": str, "fixTime": str,
                     "symbol": str, "category": str, "timeOffset": str}, ... ],
        "areas":  [ {"kind": "tcWindArea"|"tcForecastArea"|"tcWarningArea"|
                             "tcWatchArea",
                     "polygons": [ [ring, ...], ... ],  # ring = [[lon,lat],...]
                     "areaType": str, "extent": str, "windType": str,
                     "marineType": str, "fixType": str, "fixTime": str}, ... ]
      }

Every polygon is kept as a list of rings so holes (gml:innerBoundaryIs) are
preserved alongside the outer boundary (gml:outerBoundaryIs); this matches
how visualize.html feeds L.polygon (outer ring first, holes after).

Usage:
    python build_gml_dataset.py
    python build_gml_dataset.py --data-dir data --out-dir viz_data
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

NAMESPACES = {
    "tc": "http://www.bom.gov.au/dtd/tc",
    "gml": "http://www.opengis.net/gml",
}

AREA_TAGS = ["tcWindArea", "tcForecastArea", "tcWarningArea", "tcWatchArea"]


def text_of(parent, tag):
    el = parent.find(f"tc:{tag}", NAMESPACES)
    return el.text.strip() if el is not None and el.text else None


def parse_coord_list(text):
    """Parse a gml:coordinates blob (whitespace/newline-separated 'lon,lat'
    pairs) into [[lon, lat], ...]."""
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
    coords_el = line_string.find("gml:coordinates", NAMESPACES) if line_string is not None else None
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
    """Return one polygon as a list of rings; outer ring first, then any
    holes (gml:innerBoundaryIs)."""
    rings = []
    outer = polygon_el.find("gml:outerBoundaryIs/gml:LinearRing/gml:coordinates", NAMESPACES)
    if outer is not None:
        rings.append(parse_coord_list(outer.text))
    for inner in polygon_el.findall("gml:innerBoundaryIs/gml:LinearRing/gml:coordinates", NAMESPACES):
        rings.append(parse_coord_list(inner.text))
    return [r for r in rings if r]


def parse_area(area_el, kind):
    polygons = []
    for polygon_el in area_el.findall("tc:geometry/gml:polygonMember/gml:Polygon", NAMESPACES):
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
    coords = box.findall("gml:coord", NAMESPACES)
    points = []
    for coord in coords:
        x_el = coord.find("gml:X", NAMESPACES)
        y_el = coord.find("gml:Y", NAMESPACES)
        if x_el is None or y_el is None or x_el.text is None or y_el.text is None:
            continue
        points.append([float(x_el.text), float(y_el.text)])
    return points or None


def parse_bulletin(path):
    root = ET.parse(path).getroot()

    tracks = [parse_track(t) for t in root.findall("tc:tcTrack", NAMESPACES)]
    fixes = [parse_fix(f) for f in root.findall("tc:tcFix", NAMESPACES)]

    areas = []
    for kind in AREA_TAGS:
        for area_el in root.findall(f"tc:{kind}", NAMESPACES):
            areas.append(parse_area(area_el, kind))

    return {
        "distId": text_of(root, "distId"),
        "distName": text_of(root, "distName"),
        "source": os.path.basename(path),
        "fcastTime": text_of(root, "fcastTime"),
        "issueTime": text_of(root, "issueTime"),
        "expiryHrs": text_of(root, "expiryHrs"),
        "bounds": parse_bounds(root),
        "tracks": tracks,
        "fixes": fixes,
        "areas": areas,
    }


def region_name(dir_name):
    # "NT_GMLs" -> "NT"
    return dir_name[:-len("_GMLs")] if dir_name.endswith("_GMLs") else dir_name


def build(data_dir, out_dir):
    if not os.path.isdir(data_dir):
        raise SystemExit(f"Error: data directory not found: {data_dir}")

    region_dirs = sorted(
        d for d in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, d))
    )
    if not region_dirs:
        raise SystemExit(f"Error: no region subdirectories found under {data_dir}")

    os.makedirs(out_dir, exist_ok=True)
    index = {"regions": {}}
    total_files = 0
    total_errors = 0

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
                bulletin = parse_bulletin(fpath)
            except ET.ParseError as exc:
                print(f"  ! skipping {fpath}: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            dist_id = bulletin["distId"] or "UNKNOWN"
            by_dist_id.setdefault(dist_id, []).append(bulletin)

        region_out_dir = os.path.join(out_dir, region)
        os.makedirs(region_out_dir, exist_ok=True)

        cyclone_entries = []
        for dist_id, bulletins in sorted(by_dist_id.items()):
            bulletins.sort(key=lambda b: b["issueTime"] or "")
            out_path = os.path.join(region_out_dir, f"{dist_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(bulletins, f)

            issue_times = [b["issueTime"] for b in bulletins if b["issueTime"]]
            cyclone_entries.append({
                "distId": dist_id,
                "distName": bulletins[-1].get("distName"),
                "bulletinCount": len(bulletins),
                "firstIssue": min(issue_times) if issue_times else None,
                "lastIssue": max(issue_times) if issue_times else None,
            })

        cyclone_entries.sort(key=lambda c: c["firstIssue"] or "")
        index["regions"][region] = cyclone_entries
        print(f"{region}: {len(gml_files)} files -> {len(cyclone_entries)} cyclones")

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"\nParsed {total_files} GML files ({total_errors} errors).")
    print(f"Wrote {out_dir}/index.json and per-cyclone JSON under {out_dir}/<REGION>/.")


def main():
    parser = argparse.ArgumentParser(
        description="Parse BOM tcData GML bulletins into the viz_data/ dataset "
                     "used by visualize.html / visualize_ol.html."
    )
    parser.add_argument("--data-dir", default="data", help="Input directory containing <REGION>_GMLs/ subfolders (default: data)")
    parser.add_argument("--out-dir", default="viz_data", help="Output directory for the built dataset (default: viz_data)")
    args = parser.parse_args()

    build(args.data_dir, args.out_dir)


if __name__ == "__main__":
    main()
