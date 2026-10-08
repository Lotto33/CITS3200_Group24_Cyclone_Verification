# Backend (FastAPI)

FastAPI service over a relational database of BoM tropical-cyclone data,
structured following common FastAPI conventions (routers versioned under
`app/api/v1/`, config under `app/core/`, persistence split into `app/models/`
and `app/schemas/`, business logic in `app/services/`).

## Quick run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
## OR run the line below if on macOS or Linux
# source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env
# place best_track.csv and GML folders under data/ (towns.xlsx ships with the app)
alembic upgrade head
python -m app.cli all
uvicorn app.main:app --reload
```
After running these commands in terminal open http://127.0.0.1:8000/docs

The full process in detail is outlined below.

## Layout

```
backend/
├── alembic.ini              # sqlalchemy.url is blank; see alembic/env.py
├── alembic/
│   ├── env.py               # takes the URL from app.core.config.settings
│   └── versions/            # schema truth lives here
├── app/
│   ├── main.py              # FastAPI() app instance, CORS, routers, pages
│   ├── cli.py               # ingest entry point (python -m app.cli)
│   ├── build_gml_dataset.py # \
│   ├── build_towns_dataset.py#  | file pipeline: raw data/ -> static JSON
│   ├── build_map_config.py  # /  for the viewers. No database.
│   ├── gml_to_geojson.py    # one GML bulletin -> GeoJSON FeatureCollection
│   ├── gen_cont_tables.py   # contingency tables from GeoJSON, packaged towns + best track
│   ├── resources/
│   │   └── towns.xlsx      # packaged TC Locations sheet used by town and table loaders
│   ├── api/
│   │   ├── deps.py          # get_db, DbSession, pagination
│   │   └── v1/
│   │       ├── router.py    # aggregates all v1 endpoint routers
│   │       └── endpoints/   # disturbances, bulletins, towns, codes, verification
│   ├── core/config.py       # Settings (env vars / .env)
│   ├── db/
│   │   ├── base.py          # DeclarativeBase + constraint naming convention
│   │   ├── columns.py       # UtcDateTime, GeoJSONType
│   │   ├── column_maps.py   # CSV header -> model attribute, written out literally
│   │   ├── session.py       # engine, SessionLocal, SQLite PRAGMAs
│   │   └── upsert.py        # dialect-dispatching bulk upsert
│   ├── models/              # ORM models, one module per domain area
│   ├── schemas/             # Pydantic response models
│   └── services/
│       ├── interpolation/   # the 15-minute grid (unchanged science)
│       └── loaders/         # the only layer that writes to the database
└── tests/
```

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
## OR run the line below if on macOS or Linux
# source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env
```

The default `DATABASE_URL` is a local SQLite file (`backend/cyclone.db`), so
nothing else needs installing. Every model is written to run unchanged on
PostgreSQL — install the extra and point `DATABASE_URL` at it:

```bash
pip install -e ".[dev,postgres]"
# DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/cyclone
```

## Data setup

The large/raw cyclone data files are not stored in Git. The TC Locations
workbook is packaged at `app/resources/towns.xlsx`; only place the remaining
raw files under `data/` at the repository root:

```text
data/
├── best_track.csv                     # BoM product IDCKMSTM0S
├── OTCR_alldata_final_external.csv    # optional, reference only
├── NT_GMLs/ QLD_GMLs/ WA_GMLs/        # the supplied GML folders
└── contingency_tables/                # optional, generator output
```

`data/processed/` holds files written by the interpolation pipeline and does
not need to be created by hand.

## Database

### Create the schema

```bash
alembic upgrade head
```

`alembic/versions/` is the source of truth. `python -m app.cli init-db` calls
`create_all` instead and exists only as a dev shortcut.

Two settings in `alembic/env.py` are load-bearing rather than stylistic:
`render_as_batch=True`, because SQLite cannot `ALTER` a constraint and Alembic
has to recreate whole tables; and the `naming_convention` in `app/db/base.py`,
because batch mode can only recreate constraints that have names.

### Populate it

```bash
python -m app.cli all          # everything, in dependency order
python -m app.cli verify       # assert the expected row counts
```

Or one source at a time:

```bash
python -m app.cli seed-codes                 # BoM code lookup tables
python -m app.cli towns                      # packaged app/resources/towns.xlsx
python -m app.cli best-track                 # data/best_track.csv
python -m app.cli otcr                       # OTCR reanalysis (reference only)
python -m app.cli gml [--region NT] [--force] # data/{NT,QLD,WA}_GMLs
python -m app.cli interpolate                # 15-minute grid
python -m app.cli verification               # score the forecasts from the database
```

A full `all` run takes roughly 12 minutes locally: about 2.5 for the ingest and
the rest for the verification, which is computed on your machine. Against a
remote server, add the network time.

### Verification

`verification` runs the contingency generator (`app/gen_cont_tables.py`) on
what the database holds -- the towns, the bulletins' watch/warning areas and
the latest interpolation run -- so the scores reflect the server's data, not
the files on whoever's machine runs it.

```bash
python -m app.cli verification --label "my run" --replace  # replace an earlier "my run"
python -m app.cli verification --interpolation-run 3       # score a specific interpolation
python -m app.cli verification --keep-table-b              # also store Table B (see below)
python -m app.cli verification --dir ../data/contingency_tables  # import CSVs instead
```

Tables A, C and D and the summaries are stored. Table B -- every relevant
town's distance to the wind radii at every 15-minute step -- is computed but
not stored unless `--keep-table-b` is given: it is ~93% of the rows (3.3M of
3.5M), nothing reads it, and it can always be regenerated.

### Re-running against a shared database

`cli all` is safe to run against a database that already holds data, including
one the whole team shares. Your data is **merged** into the server's rather
than replacing it, so there is no need to worry about overwriting what someone
else loaded:

| step | on a re-run |
|---|---|
| code tables, towns, best track, OTCR | upserted on their natural keys: new rows added, existing rows updated, **nothing deleted** |
| GML bulletins | files whose sha256 already matches are skipped; a changed file replaces only that one bulletin |
| interpolation | the previous `"cli all"` run is replaced by one recomputed from the server's best track |
| verification | the previous `"cli all"` run is replaced by one recomputed from the server's data |

Only runs labelled `"cli all"` are replaced; runs made separately under
another label are kept. A replacement happens in the same transaction as the
recompute, so a failed run leaves the old results in place.

Two consequences of merging to be aware of:

- **The last run wins for the same record.** If two people load different
  versions of the same town, observation or GML file, the later values stay.
  Keeping `data/` in sync through git (`git pull` before `cli all`) avoids
  this.
- **Removing a row from a data file does not remove it from the server.**
  Deleting data has to be done in the database directly.

### What gets loaded

| table | rows | source |
|---|---|---|
| `code_domain` / `code_value` | 13 / 116 | `TC_Database_Structure_Oct2011.pdf`, transcribed |
| `town` / `town_group_membership` | 466 / 472 | packaged `app/resources/towns.xlsx`, sheet `TC Locations` |
| `disturbance` | 1,164 | union of the best track and the bulletins |
| `best_track_observation` | 31,706 + 13,743 | `best_track.csv` + the OTCR reanalysis |
| `bulletin` / `_track` / `_fix` / `_area` | 3,448 / 6,807 / 63,126 / 30,196 | `{NT,QLD,WA}_GMLs` |
| `interpolated_point` | 60,644 | computed from the best track |
| `verification_*` | 256,964 + 79 summaries | computed from the database (68 disturbances; Table B not stored) |

## Run

```bash
uvicorn app.main:app --reload
```

- Docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health
- Map viewer: http://127.0.0.1:8000/visualize.html (`/` redirects there), with
  the repository's `data/` folder mounted at `/data` and the pages' CSS/JS at
  `/assets`
- Contingency page: http://127.0.0.1:8000/verification.html

```bash
curl "http://127.0.0.1:8000/api/v1/disturbances?season=2016-17"
curl "http://127.0.0.1:8000/api/v1/disturbances/AU201617_19U/best-track"
curl "http://127.0.0.1:8000/api/v1/disturbances/AU201617_19U/interpolated-track"
curl "http://127.0.0.1:8000/api/v1/disturbances/AU201617_19U/bulletins"
curl "http://127.0.0.1:8000/api/v1/bulletins/1/geojson"
curl "http://127.0.0.1:8000/api/v1/towns?state=WA"
curl "http://127.0.0.1:8000/api/v1/codes/cyc_type"
curl "http://127.0.0.1:8000/api/v1/verification-runs/1/summary?scope=disturbance"
```

Set `BACKEND_CORS_ORIGINS=http://localhost:8000` in `.env` for the static map
viewers to reach the API from their own origin.

## Test

```bash
pytest
ruff check app tests alembic
```

Tests that need the git-ignored files under `data/` are marked
`requires_data` and skip themselves when it is absent, so `pytest` passes on a
fresh clone. Run only the rest with `pytest -m "not requires_data"`.

## Data caveats

These are properties of BoM's data, not bugs, and code that ignores them will
be quietly wrong.

- **`0` and `NULL` mean different things.** In the radius and eye columns `0`
  is "known to be zero" (no gales in that quadrant, no eye) and `NULL` is "not
  analysed". `interpolate_best_track` branches on the difference, so the
  loaders read every CSV as raw strings (`dtype=str`,
  `keep_default_na=False`) and no measurement column has a default.
- **Missing values in the BoM CSVs are a single space**, not an empty field,
  so everything strips before testing for blank. `NAME` also has a trailing
  space.
- **`99` in a `MN_RADIUS_*_UNCERTAINTY` column means "99 km or greater"** — a
  sentinel, not a measurement. Exclude it from any average. (All four columns
  are empty in the current CSV.)
- **The mean-radius columns are effectively absent after 2016**:
  `MN_RADIUS_GF_WIND` has 22 non-blank values out of 4,383 in the project
  period, against 1,482 for `MN_RADIUS_GF_SECNE`. The quadrant columns carry
  the data, which is why the interpolator uses the mean only as a fallback.
- **The CSV and the PDF disagree on some field names** — the CSV says
  `MN_RADIUS_GF_WIND` and `MN_RADIUS_GF_WIND_METHOD` where the PDF says
  `MN_RADIUS_GF_WND` and `MN_RADIUS_GF_METHOD`. The CSV wins;
  `db/column_maps.PDF_SPELLING_ALIASES` records the mapping.
- **Some codes are not in the 2011 spec.** `PRES_WIND_RELATION_USED` carries
  `40` on 71 rows. The code tables are therefore reference data, not foreign
  keys; unknown codes are recorded in `ingest_run.stats`, never rejected.
- **GML geometry is EPSG:4283 (GDA94), not WGS84/4326.** Stored as-is and
  recorded on `bulletin.srs`; the offset is about a metre.
- **Six QLD locations appear twice in the towns sheet** at identical
  coordinates, because they belong to two town groups. Hence
  `town_group_membership`, and hence `coastal_order` living on the membership.
  `coastal_order` is a float: the sheet uses 20.1 and 20.2 to insert places
  between integers.
- **`AU202526_05U` was scored but produced nothing**, so it has an all-zero
  contingency summary rather than no row.
- **The OTCR reanalysis is reference data only.** It ends 2016-12-25 and
  contributes 58 rows inside the project period against the best track's
  4,383, so it is never the interpolation input. Columns 84-220 of that file
  are an analyst-workbook dump with repeated header names and are not
  modelled; its `MAX_REP_TIDE_ANOM_METHOD` column holds ratios rather than
  method codes, which the loader drops to NULL and reports.

## Adding a new resource

1. Add an ORM model in `app/models/`, and import it in `app/models/__init__.py`
   — Alembic autogenerate only sees what is registered on `Base.metadata`.
2. `alembic revision --autogenerate -m "..."`, then read the generated file.
3. Add a Pydantic schema in `app/schemas/`. Do not mirror the table: keep
   large payloads out of list responses.
4. Add a loader in `app/services/loaders/` if it is ingested, writing through
   `app.db.upsert.upsert_many` so it stays idempotent.
5. Add an endpoint module in `app/api/v1/endpoints/`, then register it in
   `app/api/v1/router.py`.

## Data processing

The file-based pipeline still works and is unchanged by the database:

```bash
python -m app.services.interpolation.interpolation_pipeline
```

It extracts the watch/warning systems from the GMLs, filters the best track to
the project period, and writes `data/processed/best_track_interpolated.csv`.
`python -m app.cli interpolate` runs the same functions against the database
instead, and produces the same 60,644 rows.

> The database is **additive**. `visualize.html` still reads `data/index.json`,
> `data/<REGION>/<distId>.json`, `data/towns.json` and `data/map_config.json`
> as static files (served by this app at `/data`, or by any static server), so
> those build scripts are still needed.
> Its best-track overlay is the exception: it asks
> `/disturbances/{id}/interpolated-track` first and only falls back to
> `data/best_track/<distId>.json`. Repointing the remaining layers is a
> separate change -- see
> [docs/architecture.md](../docs/architecture.md).

## Dependencies

`backend/pyproject.toml` is the source of truth. The root `requirements.txt`
is generated from it — do not edit it by hand:

```bash
pip install pip-tools
pip-compile --no-strip-extras --extra dev \
    --output-file backend/requirements.txt backend/pyproject.toml  # from repo root
```

The root `requirements.txt` is a one-line `-r backend/requirements.txt`
pointer and is not generated -- do not aim `--output-file` at it.

Add/remove a dependency by editing `[project].dependencies` (or the `dev` /
`postgres` extras) in `pyproject.toml`, then re-run the command above.
