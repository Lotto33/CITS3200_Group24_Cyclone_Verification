# Architecture

How the backend is put together, and where the map viewer's data actually
comes from.

The READMEs tell you how to *run* things ([README.md](../README.md) for the
data pipeline and the viewers, [backend/README.md](../backend/README.md) for
the service and its CLI). This document explains how the parts fit together
and why, which is the part that is easy to get wrong when adding to it.

Row counts throughout are from a full local ingest; treat them as
order-of-magnitude, not as assertions.

## The one thing to understand first: there are two pipelines

The project grew a database *underneath* an existing file-based pipeline
rather than replacing it. Both are live, both are supported, and they produce
overlapping outputs from the same raw files. Almost every "where does this
come from?" question resolves to knowing which of the two you are looking at.

```
                     data/  (git-ignored raw BoM files)
                     best_track.csv, {NT,QLD,WA}_GMLs/
                     backend/app/resources/towns.xlsx (packaged)
                              │
              ┌───────────────┴────────────────┐
              │                                │
      [A] file pipeline                 [B] database pipeline
      backend/app/build_*.py            backend/app/cli.py
              │                                │
              ▼                                ▼
      data/index.json                    19 tables in cyclone.db
      data/<REGION>/<id>.json                  │
      data/best_track/<id>.json                ▼
      data/towns.json                    FastAPI /api/v1
      data/geojson/<id>/*.geojson              │
      data/map_config.json                     │
              │                                │
              └────────────┬───────────────────┘
                           ▼
                     visualize.html
             (reads [A] for everything except
              the best-track overlay, which
              prefers [B] — see below)
```

**Pipeline A** is the original: standalone scripts that parse the raw files
and write static JSON, which the browser fetches directly. No database, no
server-side logic. `gen_cont_tables.py` also belongs here — it reads
`data/geojson/` and a best-track CSV off disk.

**Pipeline B** is the FastAPI service: loaders parse the same raw files into
a relational schema, and the API serves it. It adds what A structurally
cannot: provenance for every ingest, run-scoped interpolation and
verification, cross-cutting queries, and a place for writes to eventually
live.

Neither is deprecated. A is what the viewer mostly still reads; B is where
the project is heading. The cost of the split is that a change to the raw
data has to be pushed through both to be visible everywhere.

## Backend layering

`backend/app/` follows conventional FastAPI structure, with one rule that is
specific to this project and worth stating plainly:

> **`app/services/loaders/` is the only layer that writes to the database.**

Everything else reads. [`app/api/deps.py`](../backend/app/api/deps.py)
enforces this at the seam: `get_db()` yields a session and deliberately never
commits, so a write accidentally introduced into a route is a bug that
surfaces rather than a silent success.

| Layer | Directory | Responsibility |
|---|---|---|
| Entry point | `app/main.py` | App instance, CORS, static mounts, page routes |
| Ingest CLI | `app/cli.py` | `python -m app.cli <subcommand>`; the write path |
| Routes | `app/api/v1/endpoints/` | Read-only HTTP, registered in `router.py` |
| Dependencies | `app/api/deps.py` | `DbSession`, pagination |
| ORM models | `app/models/` | One module per domain area; tables and constraints |
| Response models | `app/schemas/` | Pydantic; deliberately *not* mirrors of tables |
| Loaders | `app/services/loaders/` | Parse raw files, upsert, record the run |
| Science | `app/services/interpolation/` | The 15-minute grid, unchanged from the original scripts |
| Build scripts | `app/build_*.py`, `app/gml_to_geojson.py`, `app/gen_cont_tables.py` | Pipeline A; live in the package but do not use the database |

Two conventions that repay attention when extending it:

- **Schemas are not table mirrors.** `best_track_observation` has 79 columns;
  `BestTrackPoint` exposes the ten anyone plots. The full row is available
  only from the single-observation route, because a list of 31,706 full rows
  is not a useful response.
- **Externally sourced enum-ish values are stored as plain strings**, never
  `sa.Enum`. BoM can add a new `windType` at any time, and a native enum would
  abort a 3,448-file ingest on one unrecognised word. Internally generated
  values (`dataset`, `outcome`, `status`, `scope`) *do* get `CheckConstraint`s
  built from the enums, because we control every value written. See
  [`app/models/enums.py`](../backend/app/models/enums.py).

## The tables

19 tables, in five groups.

| Group | Tables | Rows | Source |
|---|---|---|---|
| Reference codes | `code_domain`, `code_value` | 13 / 116 | `TC_Database_Structure_Oct2011.pdf`, transcribed |
| Towns | `town`, `town_group_membership` | 466 / 472 | packaged `backend/app/resources/towns.xlsx`, sheet `TC Locations` |
| Cyclones | `disturbance` | 1,164 | union of the best track and the bulletins |
| | `best_track_observation` | 45,449 | `best_track.csv` (31,706) + OTCR reanalysis (13,743) |
| Bulletins | `bulletin`, `bulletin_track`, `bulletin_fix`, `bulletin_area` | 3,448 / 6,807 / 63,126 / 30,196 | `{NT,QLD,WA}_GMLs/` |
| Derived | `interpolation_run`, `interpolated_point` | 1 run = 60,644 points | computed from the best track |
| | `verification_run`, `verification_pair`, `verification_summary`, `verification_*_distance`, `verification_observed_event` | varies by run | `contingency_tables/` |
| Audit | `ingest_run` | one row per load | — |

`disturbance` is the hub: bulletins, observations, interpolated points and
verification rows all hang off it, keyed by the BoM disturbance id
(`AU201819_04U`).

## Provenance: everything is run-scoped

This is the design decision that most constrains how the backend can be
extended, so it is worth being explicit about.

Every load and every computation is wrapped in a *run* row:

- **`ingest_run`** — created by the `ingest_run()` context manager in
  [`loaders/common.py`](../backend/app/services/loaders/common.py). Records
  kind, source path, the git revision of the code that ran, rows
  read/written/skipped, status, and a `stats` JSON payload carrying the
  blank-vs-zero counts, unrecognised code values and other per-column
  observations. It exists so the loaders' guarantees are checkable later
  instead of scrolling past on stdout.
- **`interpolation_run`** — the step size and wind thresholds that produced a
  grid. Every contingency number downstream depends on which values were
  used, so a grid without a run row cannot be interpreted.
- **`verification_run`** — points at the `interpolation_run` it scored.

Two consequences:

1. **Writes are idempotent.** Every loader writes through
   [`upsert_many`](../backend/app/db/upsert.py), so re-running an ingest over
   unchanged input is a no-op on row count. The GML loader additionally
   compares a sha256 of each file against the stored `content_hash` and skips
   matches unless `force=True`.
2. **Derived data is versioned, source data is not.** Re-ingesting a
   corrected `best_track.csv` overwrites observations in place, while old
   `interpolation_run`s survive. There is currently **no link from
   `interpolation_run` back to the ingest that fed it**, so a run computed
   from superseded data is indistinguishable from a current one. This is the
   main gap to close before adding user-facing uploads.

## API surface

All read-only, all under `/api/v1`. Browse `/docs` for the generated
reference; this is the shape:

| Route | Returns |
|---|---|
| `GET /disturbances` | Paginated summaries — id, name, region, season, bulletin/observation counts, `has_best_track` |
| `GET /disturbances/{id}` | The summary plus datasets held and a resolved type description |
| `GET /disturbances/{id}/best-track` | The plottable subset of the 6-hourly reanalysed track |
| `GET /disturbances/{id}/observations/{tm}` | Every BoM field for one observation, code labels resolved |
| `GET /disturbances/{id}/interpolated-track` | The 15-minute grid from the latest `interpolation_run` |
| `GET /disturbances/{id}/bulletins` | Bulletin summaries for one cyclone |
| `GET /bulletins/{id}` | One bulletin with its tracks, fixes and areas |
| `GET /bulletins/{id}/geojson` | The same bulletin shaped exactly like `gml_to_geojson` emits |
| `GET /bulletins/{id}/areas/{area_id}` | One area's geometry, when a whole bulletin is too large |
| `GET /towns`, `/towns/groups`, `/towns/{id}` | The towns layer |
| `GET /codes`, `/codes/{domain}` | BoM code lookups |
| `GET /verification-runs`, `/{id}/summary`, `/{id}/pairs` | Contingency results |

`app/main.py` also serves the pages themselves: `/visualize.html`,
`/verification.html` (from `frontend/`), the split CSS/JS at `/assets`
(`frontend/assets/`), and the repository's `data/` folder at `/data`. Serving the pages from the same origin as the API
is what lets the viewer use relative URLs for both.

## Where the visualizer gets its data

[`frontend/assets/visualize.js`](../frontend/assets/visualize.js) fetches everything with
relative URLs, so it needs `/data` and `/assets` mounted beside the page, as
the FastAPI app does. If the API itself is unreachable it degrades in one
place, covered below.

| Layer on the page | Fetched from | Produced by | Falls back to |
|---|---|---|---|
| Cyclone dropdown | `data/index.json` | `build_gml_dataset.py` | — (page cannot load without it) |
| Bulletins: tracks, fixes, areas | `data/<REGION>/<distId>.json` | `build_gml_dataset.py` | — |
| **Best-track overlay** | **`api/v1/disturbances/<id>/interpolated-track`** | `python -m app.cli interpolate` | `data/best_track/<distId>.json` |
| Towns | `data/towns.json` | `build_towns_dataset.py` | Sidebar hint, layer empty |
| Basemap tiles | `data/map_config.json` | `build_map_config.py` | Keyless (watermarked) CARTO URL |

So: **the viewer reads pipeline A for everything except the best-track
overlay.** Only that one layer has been repointed at the database.

### Why the best-track overlay is the exception

The verification is scored on the interpolated 15-minute grid, not on the raw
6-hourly BoM fixes. Drawing the 6-hourly track next to contingency numbers
computed from the 15-minute grid shows a track the numbers were never
computed against — so the page asks the API for the grid first.

The loader in `frontend/assets/visualize.js` normalises both sources into one shape
and tags it with a `source` field:

```js
{ distId, name, source: "interpolated" | "observed",
  points: [{ time, coord: [lon, lat], pressure, windSpeed, interpolated }] }
```

- `source: "interpolated"` — from the API. `interpolated: false` marks the
  points that are original BoM fixes (the *anchors*); the rest are computed.
  The polyline follows every point; markers are drawn on every point up to
  `MAX_INTERPOLATED_MARKERS` (1200) and on the anchors only above it, since a
  long cyclone produces ~2,000 points and thousands of `circleMarker`s make
  panning stutter.
- `source: "observed"` — from the static file. The raw 6-hourly fixes, which
  carry `pressure` (the interpolated grid does not).

The fallback triggers whenever the API cannot answer: the page is served by
`python -m http.server` rather than the FastAPI app, the database has not
been ingested, or `python -m app.cli interpolate` has never produced a run.
The info panel names whichever one is on screen ("interpolated 15-minute
grid, as verified" vs "raw 6-hourly BoM fixes"), so it is always visible
which track is being displayed.

### Finishing the repointing

Everything the viewer needs already exists as endpoints — `GET /disturbances`
carries exactly what `index.json` carries, and `GET /bulletins/{id}/geojson`
is explicitly shaped for these pages. Completing the move would make the
viewer reflect the database immediately instead of requiring a
`build_gml_dataset.py` run over the whole dataset, which matters as soon as
data can be added through the app. It is deliberately not done yet: pipeline
A works offline with no server, and that is still useful.

## Related reading

- [README.md](../README.md) — running the pipeline and the viewers
- [backend/README.md](../backend/README.md) — setup, CLI, endpoints, and the
  **Data caveats** section, which records the properties of BoM's files that
  code will otherwise get quietly wrong
- [`app/db/column_maps.py`](../backend/app/db/column_maps.py) — the CSV
  header → model attribute mappings, written out literally so a change in
  BoM's files shows up as a diff
