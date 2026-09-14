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
that `visualize.html` reads, and nothing about the viewers has changed.

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


### 1. Build the dataset (one-off, or whenever `data/` changes)

The GML files are parsed once into compact per-cyclone GEOJSON files so the
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