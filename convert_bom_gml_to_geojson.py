#!/usr/bin/env python3
"""Convert a BOM GML tcData file into GeoJSON for quick preview."""

import argparse
import json
import os
import xml.etree.ElementTree as ET

NAMESPACES = {
    "tc": "http://www.bom.gov.au/dtd/tc",
    "gml": "http://www.opengis.net/gml",
}


def parse_coordinates(text):
    if not text:
        return []
    coords = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 2:
            raise ValueError(f"Invalid coordinate pair: {line}")
        lon = float(parts[0])
        lat = float(parts[1])
        coords.append([lon, lat])
    return coords


def extract_polygons(root):
    polygons = []
    for polygon in root.findall(".//gml:Polygon", NAMESPACES):
        for coords_elem in polygon.findall(".//gml:coordinates", NAMESPACES):
            coords = parse_coordinates(coords_elem.text)
            if coords:
                polygons.append(coords)
    return polygons


def build_geojson(polygons, source_file):
    features = []
    for polygon in polygons:
        features.append(
            {
                "type": "Feature",
                "properties": {"source": os.path.basename(source_file)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [polygon],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def main():
    parser = argparse.ArgumentParser(description="Convert BOM tcData GML to GeoJSON.")
    parser.add_argument("input", help="Input GML file path")
    parser.add_argument("output", nargs="?", help="Output GeoJSON file path")
    args = parser.parse_args()

    output_path = args.output or os.path.splitext(args.input)[0] + ".geojson"

    tree = ET.parse(args.input)
    root = tree.getroot()
    polygons = extract_polygons(root)

    if not polygons:
        raise SystemExit("Error: no GML polygons found in the input file.")

    geojson = build_geojson(polygons, args.input)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    print(f"Written GeoJSON to: {output_path}")


if __name__ == "__main__":
    main()
