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

Both read the identical dataset produced in step 1, so they stay in sync
automatically.

### 1. Build the dataset (one-off, or whenever `data/` changes)

The GML files are parsed once into compact per-cyclone JSON files so the
browser doesn't have to parse thousands of raw XML files. The build script
lives at `backend/app/build_gml_dataset.py` — **run it from the repository
root**, not from inside `backend/app/`, since its `--data-dir`/`--out-dir`
defaults are plain relative paths resolved against your current working
directory:

```bash
python backend/app/build_gml_dataset.py
```

> `backend/app/gml_to_geojson.py` must stay alongside `build_gml_dataset.py`
> in the same folder — `build_gml_dataset.py` imports it directly
> (`import gml_to_geojson`), and Python resolves that import against the
> invoked script's own directory, not your current working directory, so
> this works correctly regardless of where you run the command from as long
> as the two files are together.

This writes `data/index.json` plus one JSON file per cyclone under
`data/<REGION>/<distId>.json`, along with the per-bulletin GeoJSON that
`backend/app/gen_cont_tables.py` consumes under `data/geojson/<distId>/`.
Generated output under `data/` besides the source GML folders is
git-ignored — regenerate it locally rather than committing it.

It also parses `data/best_track.csv` — BOM's **best track** database (the
track as re-analysed after the event, distinct from the
`Observed`/`Forecast` tracks in the GML bulletins) — and writes one
`data/best_track/<distId>.json` per disturbance the CSV covers, matched to
GML cyclones by `distId`/`DISTURBANCE_ID`. Not every cyclone has a match:
best track is only published for seasons BOM has fully reanalysed, so recent
cyclones typically won't have one yet. Cyclones with a match are flagged
`"hasBestTrack": true` in `data/index.json`. Pass `--best-track-csv ''` to
skip this step, or `--best-track-csv <path>` to point at a different CSV.

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

Best track (`data/best_track/<distId>.json`) captures every point BOM's CSV
records for that disturbance: `time`, `coord` (`[lon, lat]`), `pressure`
(`CENTRAL_PRES`), and `windSpeed` (`MAX_WIND_SPD`), sorted by time. It's
per-cyclone, not per-bulletin — one fixed post-event track, independent of
which bulletin is currently on screen.

### 3. Generate contingency tables

`backend/app/gen_cont_tables.py` builds Tables A–D and the hit/miss/false
alarm/correct-negative contingency summary for a single disturbance ID,
comparing forecast watch/warning areas (from step 1's GeoJSON output) against
observed gales (from the best-track CSV). Unlike `build_gml_dataset.py`, its
data paths are resolved from `__file__` rather than the current working
directory, so it can be run from anywhere — the repo root or elsewhere:

```bash
python backend/app/gen_cont_tables.py AU202526_34U
```

Optional flags:

```bash
python backend/app/gen_cont_tables.py AU202526_34U \
  --output-dir data/contingency_tables \
  --x-hours 0 \
  --y-hours 24
```

#### Filter results by state or season

To generate statistics for one Australian state, use `--state` with the
state value stored in `data/towns.xlsx`:

```bash
python backend/app/gen_cont_tables.py AU202526_34U --state WA
```

The state filter is applied to the `State` column from the `TC Locations`
sheet in `data/towns.xlsx` before any tables are generated. Only matching
locations are passed through Tables A, B, C, and D. `State` is used for
filtering but is not included as a column in Table A or Table D. The filter is
not inferred from the cyclone's path or from the GML source region.

To generate a combined contingency table for every disturbance in a
Jul–Jun cyclone season, use `--season` without a disturbance ID:

```bash
python backend/app/gen_cont_tables.py --season 2025-26
```

The season is derived from each forecast base time (`fcastTime`): July to
December starts the named season, while January to June belongs to the
previous year's season. For example, `2025-26` covers July 2025 through June
2026.

The filters can be combined. This generates all disturbances in the season,
then reports the final contingency statistics for one state:

```bash
python backend/app/gen_cont_tables.py --season 2025-26 --state WA
```

If a disturbance ID is supplied along with `--season`, the explicitly supplied
disturbance ID is used; use `--season` on its own to select a whole season.

- `disturbance_id` (positional, required) — the BOM disturbance ID, e.g.
  `AU202526_34U`.
- `--output-dir` (default `data/contingency_tables`) — where the generated
  CSVs are written.
- `--state` — generate Tables A-D using only locations whose `State` column in
  the `TC Locations` sheet matches the supplied value (for example, `WA`).
- `--season` — select all disturbances whose forecast base times fall in a
  Jul–Jun season (for example, `2025-26`).
- `--x-hours` / `--y-hours` (default `0` / `24`) — the window, relative to
  each forecast base time, in which an observed gale counts as a "hit"
  against that forecast.

This writes `<disturbance_id>_table_a.csv` through `_table_d.csv`,
`<disturbance_id>_contingency_matrix.csv`, and
`<disturbance_id>_contingency_summary.csv` under `--output-dir`, and prints
progress plus the final contingency stats and matrix to the console as it
runs.

Requires step 1 (`build_gml_dataset.py`) to have already been run — it reads
the `data/geojson/<distId>/` files that step produces — plus the `TC Locations`
sheet in `data/towns.xlsx` and a best-track CSV. If
`data/processed/best_track_interpolated.csv` exists, it is preferred because
it already contains the significant-cyclone filtering and interpolation. If
it does not exist, the script falls back to `data/best_track.csv` and performs
the interpolation locally.

If you only need one of Tables A–D rather than the full run, the individual
`generate_table_a()` / `generate_table_b()` / `generate_table_c()` /
`generate_table_d()` functions can be imported and called directly; Table C
also accepts an already-computed Table B via its `table_b=` parameter to
avoid rebuilding it (Table B is the most expensive of the four to compute).

#### NOTE THAT RUNNING IT STRAIGHT FROM THE TERMINAL IS FOR TESTING ONLY. TODO: IMPLEMENT FRONTEND TO REQUEST THIS CODE BE RUN. 

### Notes

- `backend/app/gml_to_geojson.py` converts a single GML bulletin's features
  into a standalone GeoJSON `FeatureCollection`; `build_gml_dataset.py`
  imports and reuses it to write the per-bulletin GeoJSON under
  `data/geojson/` that `gen_cont_tables.py` consumes, so there is one shared
  implementation rather than two that could drift apart.
- `python backend/app/build_gml_dataset.py --data-dir data --out-dir data`
  accepts custom input/output paths if needed (both shown here at their
  defaults).
- In the viewers, GML `tcTrack` styling distinguishes the two `trackType`
  values: **Forecast** is solid, **Observed** is dashed. The best-track
  overlay (green, toggleable via the "Best track (post-event)" layer) is a
  separate line drawn from the CSV data described above, not a `trackType`
  value — cyclones with one are marked ★ in the cyclone dropdown.
- `tcWindArea` polygons distinguish their `fixType`: **Current** areas are
  red and **Forecast** areas are blue.