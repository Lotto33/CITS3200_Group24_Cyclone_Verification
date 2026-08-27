# CITS3200_Group24_Cyclone_Verification

## Group Members 

|  Name | Student ID | GitHub Username |
| ------------ | ---------- | --------------- |
| Elliott Naidoo  | 24313893   | Lotto33     |
| Eliza Hutchens | 24230437   | arcococoa |
| Scout Wu | 24729742 | Exusiai101 |
| Siyu Zhu | 24439408 | LZhuSY  |
| Kahlea Aslanis | 23788447 | kahleaa |
| Michael Kartika | 24239793 | mrdudman |



## Visualizing the BOM cyclone GML data

`data/NT_GMLs`, `data/QLD_GMLs`, `data/WA_GMLs` contain ~3,450 individual BOM
`tcData` GML bulletins. Two self-contained map viewers (no build step, no
framework) browse them interactively — pick a cyclone/event and step or play
through its bulletins to see the track, position fixes,
and wind/forecast/warning/watch areas. Where available, the post-event
**best track** (see below) is overlaid too.

Cyclones are presented in one list rather than filtered by state. If an event
appears in more than one regional BOM dataset, the viewer combines those
bulletins into a single timeline.

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

It also parses `data/Database of Past tropical cyclone tracks.csv` — BOM's
**best track** database (the track as re-analysed after the event, distinct
from the `Observed`/`Forecast` tracks in the GML bulletins) — and writes one
`viz_data/best_track/<distId>.json` per disturbance the CSV covers, matched
to GML cyclones by `distId`/`DISTURBANCE_ID`. Not every cyclone has a match:
best track is only published for seasons BOM has fully reanalysed, so recent
cyclones typically won't have one yet. Cyclones with a match are flagged
`"hasBestTrack": true` in `viz_data/index.json`. Pass `--best-track-csv ''`
to skip this step, or `--best-track-csv <path>` to point at a different CSV.

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

Best track (`viz_data/best_track/<distId>.json`) captures every point BOM's
CSV records for that disturbance: `time`, `coord` (`[lon, lat]`),
`pressure` (`CENTRAL_PRES`), and `windSpeed` (`MAX_WIND_SPD`), sorted by
time. It's per-cyclone, not per-bulletin — one fixed post-event track,
independent of which bulletin is currently on screen.

### Notes

- `backend/app/gml_to_geojson.py` converts every GML bulletin into an
  individual `data/geojson/<source-file>.geojson` FeatureCollection for the
  backend contingency-table logic. Run it from the repository root with
  `python -m backend.app.gml_to_geojson`.
- `convert_bom_gml_to_geojson.py` is a small single-file polygon preview tool
  for QGIS and is not part of either bulk pipeline.
- Keep `build_gml_dataset.py` for the browser viewers. It produces a different
  schema (`viz_data/`) and also builds the browser index and best-track files;
  it cannot be replaced by the GeoJSON converter without rewriting the
  viewers.
- `build_gml_dataset.py --data-dir data --out-dir viz_data` accepts custom
  input/output paths if needed.
- In the viewers, GML `tcTrack` styling distinguishes the two `trackType`
  values: **Forecast** is solid, **Observed** is dashed. The best-track
  overlay (green, toggleable via the "Best track (post-event)" layer) is a
  separate line drawn from the CSV data described above, not a `trackType`
  value — cyclones with one are marked ★ in the cyclone dropdown.
- `tcWindArea` polygons distinguish their `fixType`: **Current** areas are
  red and **Forecast** areas are blue.
