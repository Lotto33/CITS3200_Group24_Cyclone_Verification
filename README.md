# CITS3200_Group24_Cyclone_Verification

## Visualizing the BOM cyclone GML data

`data/NT_GMLs`, `data/QLD_GMLs`, `data/WA_GMLs` contain ~3,450 individual BOM
`tcData` GML bulletins. Two self-contained map viewers (no build step, no
framework) browse them interactively — pick a region, pick a cyclone/event,
and step or play through its bulletins to see the track, position fixes,
and wind/forecast/warning/watch areas:

- `visualize.html` — built on [Leaflet](https://leafletjs.com/).
- `visualize_ol.html` — the same viewer built on
  [OpenLayers](https://openlayers.org/) instead, with an extra "data-retention
  check" panel that shows exactly which GML fields survived into the JSON
  for the bulletin on screen, plus the raw JSON itself.

Both read the identical `viz_data/` dataset produced in step 1, so they stay
in sync automatically.

### 1. Build the dataset (one-off, or whenever `data/` changes)

The GML files are parsed once into compact per-cyclone JSON files so the
browser doesn't have to parse thousands of raw XML files:

```bash
python build_gml_dataset.py
```

This writes `viz_data/index.json` plus one JSON file per cyclone under
`viz_data/<REGION>/<distId>.json`. `viz_data/` is git-ignored — regenerate
it locally rather than committing it.

# **Warning:** This is a working but wrong conversion

# **Warning:** This is a working but wrong conversion

# **Warning:** This is a working but wrong conversion

### 2. Serve the page

Browsers block `fetch()` of local files opened via `file://`, so serve the
folder with any simple static server, e.g.:

```bash
python -m http.server 8000
```

Then open [http://localhost:8000/visualize.html](http://localhost:8000/visualize.html) (Leaflet) or
[http://localhost:8000/visualize_ol.html](http://localhost:8000/visualize_ol.html) (OpenLayers).

### Data retention

`build_gml_dataset.py` captures every field present in the source GML:
`distId`, `distName`, `fcastTime`, `issueTime`, `expiryHrs`, `source`
filename, the `gml:boundedBy` envelope, every `tcTrack` (coords, trackType,
start/end time), every `tcFix` (coord, fixType, fixTime, symbol, category,
timeOffset), and every `tcWindArea` / `tcForecastArea` / `tcWarningArea` /
`tcWatchArea` (all polygon rings including holes, areaType, extent,
windType, marineType, fixType, fixTime). Nothing in the GML schema is
dropped except the fixed `xsi:schemaLocation`/namespace declarations, which
carry no per-bulletin data. `visualize_ol.html`'s "Data-retention check"
panel verifies this live, per bulletin, against the raw JSON.

### Notes

- `convert_bom_gml_to_geojson.py` converts a single GML file's wind-area
  polygons to a standalone GeoJSON file (e.g. for QGIS) — unrelated to the
  bulk viewers above.
- `build_gml_dataset.py --data-dir data --out-dir viz_data` accepts custom
  input/output paths if needed.
