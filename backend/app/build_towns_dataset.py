#!/usr/bin/env python3
"""Build the towns dataset (for visualize.html's Towns layer) from
data/towns.xlsx.

visualize.html is a static page served over plain HTTP -- it cannot read an
xlsx. So, like build_gml_dataset.py, this script does the parsing offline and
writes plain JSON into data/ for the page to fetch.

Reads the "TC Locations" sheet, which is the same sheet gen_cont_tables.py
uses, so the towns drawn on the map are exactly the locations the contingency
tables are scored against. (The workbook's other sheet,
"townsandcities_20250515", stores coordinates in Web Mercator metres and is
deliberately not used here.)

Writes:

  data/towns.json
      {"sheet": "TC Locations", "count": <n>, "towns": [
         {name, state, lat, lon, group, coastalOrder, major, island}, ...]}

Usage:
    python build_towns_dataset.py
    python build_towns_dataset.py --towns-xlsx data/towns.xlsx --out-dir data
"""

import argparse
import json
import math
import os
import sys

import pandas as pd

DEFAULT_SHEET = "TC Locations"

# Sheet column -> JSON key. Everything else in the sheet (Island Major,
# Island Territory, ...) is not needed by the map.
NAME_COLUMN = "Name"
STATE_COLUMN = "State"
LAT_COLUMN = "Latitude"
LON_COLUMN = "Longitude"
GROUP_COLUMN = "Town Group"
COASTAL_ORDER_COLUMN = "Coastal Order"
MAJOR_COLUMN = "Major Town"
ISLAND_COLUMN = "Island Town"


def clean_str(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def clean_flag(value):
    """The trailing flag columns are sparse -- '1' where the flag applies and
    blank otherwise -- so anything non-empty and non-zero counts as True."""
    text = clean_str(value)
    return bool(text) and text not in {"0", "0.0"}


def clean_int(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def has_valid_coords(lat, lon):
    """The sheet carries formatted-but-empty rows below the real data whose
    coordinates come through as NaN. Drop those, and anything outside the
    valid lat/lon range, rather than letting them reach the map."""
    if lat is None or lon is None:
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def load_towns(xlsx_path, sheet):
    if not os.path.isfile(xlsx_path):
        raise SystemExit(f"Error: towns workbook not found: {xlsx_path}")
    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
    except ValueError as exc:
        raise SystemExit(
            f"Error: could not read sheet {sheet!r} from {xlsx_path}: {exc}"
        ) from exc

    missing = [c for c in (NAME_COLUMN, LAT_COLUMN, LON_COLUMN) if c not in df.columns]
    if missing:
        raise SystemExit(
            f"Error: sheet {sheet!r} is missing required column(s): {', '.join(missing)}"
        )

    towns = []
    skipped = 0
    for row in df.to_dict("records"):
        name = clean_str(row.get(NAME_COLUMN))
        lat = pd.to_numeric(row.get(LAT_COLUMN), errors="coerce")
        lon = pd.to_numeric(row.get(LON_COLUMN), errors="coerce")
        lat = float(lat) if pd.notna(lat) else None
        lon = float(lon) if pd.notna(lon) else None
        if not name or not has_valid_coords(lat, lon):
            skipped += 1
            continue
        towns.append(
            {
                "name": name,
                "state": clean_str(row.get(STATE_COLUMN)),
                "lat": lat,
                "lon": lon,
                "group": clean_str(row.get(GROUP_COLUMN)),
                "coastalOrder": clean_int(row.get(COASTAL_ORDER_COLUMN)),
                "major": clean_flag(row.get(MAJOR_COLUMN)),
                "island": clean_flag(row.get(ISLAND_COLUMN)),
            }
        )

    towns.sort(key=lambda t: (t["state"] or "", t["name"]))
    return towns, skipped


def build(xlsx_path, sheet, out_dir):
    towns, skipped = load_towns(xlsx_path, sheet)
    if not towns:
        raise SystemExit(
            f"Error: no usable rows found in sheet {sheet!r} of {xlsx_path}"
        )

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "towns.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"sheet": sheet, "count": len(towns), "towns": towns}, f)

    print(
        f"{xlsx_path} [{sheet}]: {len(towns)} towns ({skipped} row(s) skipped: missing name or invalid coordinates)"
    )
    print(f"Wrote {out_path}.")
    if skipped:
        print(
            "Skipped rows are expected -- the sheet has formatted-but-empty trailing rows.",
            file=sys.stderr,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Parse the towns workbook into data/towns.json for visualize.html's Towns layer."
    )
    parser.add_argument(
        "--towns-xlsx",
        default="data/towns.xlsx",
        help="Path to the towns workbook (default: data/towns.xlsx)",
    )
    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET,
        help=f"Worksheet to read (default: {DEFAULT_SHEET!r})",
    )
    parser.add_argument(
        "--out-dir",
        default="data",
        help="Output directory for towns.json (default: data)",
    )
    args = parser.parse_args()
    build(args.towns_xlsx, args.sheet, args.out_dir)


if __name__ == "__main__":
    main()
