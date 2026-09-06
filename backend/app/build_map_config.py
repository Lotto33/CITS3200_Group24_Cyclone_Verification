#!/usr/bin/env python3
"""Build data/map_config.json -- the basemap settings visualize.html fetches
at startup.

CARTO's raster basemaps now watermark tiles requested without an API key. The
page is a static file with no bundler or backend behind it, so it cannot read
a .env; this script resolves the key offline and bakes it into a JSON file
under data/ (which is git-ignored, so the key never reaches the repo).

The key is read from the CARTO_API_KEY environment variable, falling back to a
KEY=value .env file at the repo root. With no key at all this still writes a
usable config using the keyless URL -- a teammate who has not set up .env gets
a watermarked map, not a broken one.

Writes:

  data/map_config.json
      {"basemapUrl": "...", "attribution": "...", "subdomains": "abcd",
       "maxZoom": 19, "hasApiKey": true|false}

Usage:
    python build_map_config.py
    python build_map_config.py --env-file .env --style dark_all --out-dir data
"""

import argparse
import json
import os
import sys

# CARTO raster basemap styles. The key goes in a "key" query parameter --
# not "api_key". See https://docs.carto.com/faqs/carto-basemaps
BASEMAP_URL = "https://{s}.basemaps.cartocdn.com/%s/{z}/{x}/{y}{r}.png"
STYLES = ["dark_all", "light_all", "rastertiles/voyager"]
DEFAULT_STYLE = "dark_all"
ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; CARTO'
ENV_VAR = "CARTO_API_KEY"


def read_env_file(path):
    """Minimal KEY=value parser -- enough for a .env of a few lines, and it
    keeps this script free of a python-dotenv dependency like the other
    build_*.py scripts."""
    values = {}
    if not path or not os.path.isfile(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_api_key(env_file):
    # An explicitly exported variable beats the file, so CI can inject a key
    # without writing one to disk.
    key = os.environ.get(ENV_VAR, "").strip()
    if key:
        return key, "environment"
    key = read_env_file(env_file).get(ENV_VAR, "").strip()
    if key:
        return key, env_file
    return None, None


def build(env_file, style, out_dir):
    api_key, source = resolve_api_key(env_file)
    url = BASEMAP_URL % style
    if api_key:
        url = f"{url}?key={api_key}"

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "map_config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "basemapUrl": url,
            "attribution": ATTRIBUTION,
            "subdomains": "abcd",
            "maxZoom": 19,
            "hasApiKey": bool(api_key),
        }, f, indent=2)

    if api_key:
        print(f"CARTO basemap style {style!r} with API key from {source}.")
    else:
        print(
            f"! No {ENV_VAR} found (checked the environment and {env_file}).\n"
            f"  Wrote a keyless config -- CARTO will watermark the tiles.\n"
            f"  Copy .env.example to .env and add your key from https://carto.com/basemaps/apikey/",
            file=sys.stderr,
        )
    print(f"Wrote {out_path}.")


def main():
    parser = argparse.ArgumentParser(
        description="Write data/map_config.json (basemap URL + CARTO API key) for visualize.html."
    )
    parser.add_argument("--env-file", default=".env", help="File to read CARTO_API_KEY from (default: .env)")
    parser.add_argument("--style", default=DEFAULT_STYLE, choices=STYLES, help=f"CARTO raster basemap style (default: {DEFAULT_STYLE})")
    parser.add_argument("--out-dir", default="data", help="Output directory for map_config.json (default: data)")
    args = parser.parse_args()
    build(args.env_file, args.style, args.out_dir)


if __name__ == "__main__":
    main()
