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



## The backend database and API

`backend/` holds a FastAPI service over a relational database of everything in
`data/`: the BoM best track, the code lookup tables from
`data/TC_Database_Structure_Oct2011.pdf`, the GML bulletins, the towns layer,
the interpolated 15-minute track, and the contingency tables.

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head        # create the schema (SQLite by default, no setup)
python -m app.cli all       # seed and ingest everything (~2.5 min)
python -m app.cli verify    # assert the expected row counts
uvicorn app.main:app --reload
```

Then browse http://127.0.0.1:8000/docs.

See [backend/README.md](backend/README.md) for the CLI, the endpoints, and --
worth reading before using the data -- the **Data caveats** section, which
records the things about BoM's files that code will otherwise get quietly
wrong: `0` versus `NULL` in the radius columns, missing values written as a
single space, the `99` sentinel, GDA94 rather than WGS84 geometry, and the six
town names that appear twice.

The database is **additive**: the build scripts below still produce the JSON
that `visualize.html` reads for its cyclone list, bulletins and towns. The one
layer that now comes from the database instead is the best-track overlay --
see [Data sources](#data-sources) below.

[docs/architecture.md](docs/architecture.md) explains how the two pipelines,
the backend layers and the viewer's data sources fit together.

## The verification page (`verification.html`)

Unlike the viewers below, this page is generated code: it is written in
TypeScript under `frontend/src/` and compiled to `assets/verification.js`,
which is what `verification.html` and the FastAPI app actually serve. It
calls `POST /api/v1/contingency-tables/` to build a real contingency table
and skill scores for a cyclone/season/state selection. Rebuild it after
editing the source:

```bash
cd frontend
npm install
npm run build     # or: npm run watch
```

The compiled `assets/verification.js` is committed, so this step is only
needed when changing `frontend/src/verification.ts`.

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

### Data sources

`visualize.html` never reads GML or CSV directly. Almost everything it draws
is pre-built JSON under `data/`, which the build scripts below produce from
the raw files:

| Fetched by the page | Built by | Raw source |
| --- | --- | --- |
| `data/index.json` (cyclone list) | `backend/app/build_gml_dataset.py` | `data/NT_GMLs/`, `data/QLD_GMLs/`, `data/WA_GMLs/` (`productfile.*.gml`) |
| `data/<REGION>/<distId>.json` (bulletins: tracks, fixes, areas) | `backend/app/build_gml_dataset.py` | same GML folders; only cyclones with at least one watch/warning area |
| `data/best_track/<distId>.json` (best-track overlay, fallback only) | `backend/app/build_gml_dataset.py` | `data/best_track.csv` (BoM IDCKMSTM0S), matched on `DISTURBANCE_ID` |
| `data/towns.json` (Towns layer) | `backend/app/build_towns_dataset.py` | `TC Locations` sheet of `data/towns.xlsx` |
| `data/map_config.json` (basemap tile URL) | `backend/app/build_map_config.py` | `CARTO_API_KEY` in `.env` |

The one exception is the best-track overlay. The verification is scored on
the interpolated 15-minute grid, so the page asks
`/api/v1/disturbances/<distId>/interpolated-track` for it first and only falls
back to the raw 6-hourly `data/best_track/<distId>.json` when that route is
unavailable -- served from `python -m http.server` rather than the FastAPI
app, or before `python -m app.cli interpolate` has produced a run. The info
panel names whichever one is on screen.

Not used by the viewer: `data/OTCR_alldata_final_external.csv`,
`data/processed/*.csv`, `data/contingency_tables/*.csv` and `data/geojson/`
(built alongside the viewer JSON, but consumed by `gen_cont_tables.py`).

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

### 2. Build the towns layer and the basemap config

The viewers overlay BOM's tropical-cyclone locations (the **Towns** layer) so
you can see where a cyclone sits relative to populated places. They come from
the `TC Locations` sheet of `data/towns.xlsx` — the same sheet
`gen_cont_tables.py` scores against, so the map and the contingency tables
refer to the same set of locations. As with the GML data, the browser can't
read an xlsx, so parse it once into JSON (**from the repository root**):

```bash
python backend/app/build_towns_dataset.py
```

This writes `data/towns.json` (~470 locations, each with name, state,
lat/lon, town group, coastal order, and major/island flags). Rows with a
missing name or missing/invalid coordinates are skipped — the sheet has
formatted-but-empty trailing rows, so a skipped count in the hundreds is
expected, not an error.

CARTO stamps an "API KEY REQUIRED" watermark across every basemap tile it
serves without an API key. Free-tier keys are available at
[carto.com/basemaps/apikey](https://carto.com/basemaps/apikey/). Copy the
example env file, paste your key into it, and generate the config the page
reads:

```bash
cp .env.example .env      # then set CARTO_API_KEY=... in .env
python backend/app/build_map_config.py
```

This writes `data/map_config.json` with the tile URL. Both `.env` and `data/`
are git-ignored, so the key never lands in the repository. Both steps are
optional: without `data/towns.json` the Towns layer shows a hint in the
sidebar instead of dots, and without `data/map_config.json` the map falls
back to the keyless (watermarked) basemap. The rest of the viewer works
either way.

### 3. Serve the page

Browsers block `fetch()` of local files opened via `file://`, so the page has
to be served over HTTP. The FastAPI backend serves `visualize.html` and the
`data/` folder alongside the API:

```bash
cd backend
uvicorn app.main:app --reload
```

Then open [http://localhost:8000/visualize.html](http://localhost:8000/visualize.html)
(`/` redirects there). The page still reads the JSON built in steps 1 and 2
for its cyclone list, bulletins and towns, so those steps are still required.
Only the best-track overlay comes from the database, and it falls back to
`data/best_track/<distId>.json` when the API cannot answer.

Any static server on the repository root works too, e.g.
`python -m http.server 8000` -- the viewer works there, with the best-track
overlay falling back to the 6-hourly fixes. That is also how to open
[visualize_ol.html](http://localhost:8000/visualize_ol.html) (OpenLayers).

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

### 4. Generate contingency tables

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

- `disturbance_id` (optional when `--season` is supplied) — one or more BOM
  disturbance IDs, e.g. `AU202526_34U`. If omitted, `--season` must be used
  to select all disturbances in that Jul–Jun season.
- `--output-dir` (default `data/contingency_tables`) — where the generated
  CSVs are written.
- `--state` — generate Tables A-D using only locations whose `State` column in
  the `TC Locations` sheet matches the supplied value (for example, `WA`).
- `--season` — select all disturbances whose forecast base times fall in a
  Jul–Jun season (for example, `2025-26`).
- `--coastal-buffer-km` (default `6.0`) — distance from a watch/warning edge
  within which a coastal location counts as covered for eligible bulletins.
- `--coastal-buffer-cutoff` (default `2025-06-01`) — date from which the
  coastal buffer is disabled.
- `--relevance-km` (default `300.0`) — maximum distance from a watch/warning
  area for a location to be included in Table A.
- `--x-hours` / `--y-hours` (default `0` / `24`) — the window, relative to
  each forecast base time, in which an observed gale counts as a "hit"
  against that forecast.

This writes dated, filter-aware CSVs under `--output-dir`. For example, a WA
run generated on 11 September 2026 produces names such as
`AU202526_34U_state-WA_date-20260911_table_a.csv` through
`_table_d.csv`, plus the corresponding contingency matrix and summary files.
Season-selected combined runs include the season too, for example
`combined_season-2025-26_state-WA_date-20260911_table_d.csv`. If no state or
season filter is applied, those filter components are omitted. The run date is
the date on which the CSVs are generated.

Progress plus the final contingency stats and matrix are also printed to the
console as the script runs.

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
  overlay (teal, toggleable via the "Best track (interpolated grid, or raw
  fixes)" layer) is a separate line, not a `trackType` value — cyclones with
  a best track are marked ★ in the cyclone dropdown. It prefers the
  interpolated 15-minute grid from the API and falls back to the 6-hourly CSV
  data described above.
- `tcWindArea` polygons distinguish their `fixType`: **Current** areas are
  red and **Forecast** areas are blue.
- Town dots are drawn once at startup into their own Leaflet pane above the
  cyclone polygons, and are deliberately excluded from the zoom-to-cyclone
  bounds calculation — selecting a cyclone still frames that cyclone, not all
  of Australia. Hover a dot for its name, click it for state, coordinates,
  town group, coastal order, and major/island flags. Major towns are drawn
  slightly larger and white.
- `python backend/app/build_map_config.py --style light_all` switches the
  basemap to CARTO's light style (`dark_all`, `light_all` and
  `rastertiles/voyager` are supported); `--env-file` points at a different
  env file. `CARTO_API_KEY` set in the environment takes precedence over
  `.env`, so CI can inject a key without writing one to disk.