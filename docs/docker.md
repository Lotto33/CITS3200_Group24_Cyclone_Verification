# Running the app with Docker

The repository ships a `Dockerfile` and a `docker-compose.yml` that run the
whole app (FastAPI backend, the HTML pages, and the SQLite database) in one
container. The only thing you provide is the `data/` folder, which is mounted
into the container.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS)
  or Docker Engine with the Compose plugin (Linux).
- The `data/` folder (BoM GML archives and `best_track.csv`), placed at the
  repository root. It is git-ignored, so it is not in a fresh clone; ask the
  team for a copy, or upload an archive through the app once it is running.
  The app starts without it, but the map and verification pages stay empty.

## Quick start

From the repository root:

```bash
docker compose up --build
```

Then open <http://localhost:8000>. Also useful:

| URL | What |
| --- | --- |
| <http://localhost:8000/> | Home page |
| <http://localhost:8000/visualize.html> | Cyclone map viewer |
| <http://localhost:8000/verification.html> | Verification page |
| <http://localhost:8000/docs> | Interactive API docs |
| <http://localhost:8000/health> | Health check |

On start-up the container (`startup.sh`) creates `data/gml`, `data/uploads` and
`data/geojson`, writes `data/map_config.json`, applies the database migrations
(`alembic upgrade head`) and starts `uvicorn` on `0.0.0.0:8000`.

Run in the background with `docker compose up -d --build`, and stop with
`docker compose down`.

### Without Compose

```bash
docker build -t cyclone-verification .

# macOS / Linux / Git Bash
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data" cyclone-verification
```

```powershell
# Windows PowerShell
docker run --rm -p 8000:8000 -v "${PWD}/data:/app/data" cyclone-verification
```

## Loading the data

A fresh `data/` folder only holds your inputs. Build everything the app reads
by running the same commands as in the main [README](../README.md), but inside
the running container:

```bash
# 1. Database: seed, ingest and score everything (~12 minutes)
docker compose exec -w /app/backend app python -m app.cli all
docker compose exec -w /app/backend app python -m app.cli verify

# 2. Map pages: per-cyclone JSON and the towns layer (run from /app, the default)
docker compose exec app python backend/app/build_gml_dataset.py
docker compose exec app python backend/app/build_towns_dataset.py
```

Outputs are written under `data/` on your host, so they survive restarts and
rebuilds. Expected inputs in `data/`: `best_track.csv`, the `NT_GMLs`,
`QLD_GMLs` and `WA_GMLs` folders, and optionally
`OTCR_alldata_final_external.csv`.

## Configuration

Set variables in a `.env` file next to `docker-compose.yml` (picked up
automatically if present; see `.env.example`) or under `environment:` in the
compose file.

| Variable | Default in the image | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `/app/data` | Where data, uploads and generated files live. Keep it at `/app/data`: a few modules assume `<repo>/data`. |
| `DATABASE_URL` | `sqlite+pysqlite:////app/data/cyclone.db` | Database. The default keeps the SQLite file on the mounted volume. For Postgres use `postgresql+psycopg://user:pass@host:5432/dbname`. |
| `CARTO_API_KEY` | unset | Removes the CARTO "API KEY REQUIRED" watermark from the basemap. Written into `data/map_config.json` on start-up. |
| `BACKEND_CORS_ORIGINS` | backend default | Allowed CORS origins, if the API is called from another origin. |

To change the host port, edit `ports:` in `docker-compose.yml`
(for example `"9000:8000"`).

## Everyday commands

```bash
docker compose logs -f app          # follow logs
docker compose exec app bash        # shell inside the container
docker compose restart app          # restart after changing .env
docker compose up -d --build        # rebuild after code changes
docker compose down                 # stop and remove the container
```

The database and all data live in `./data`, not in the container, so
`docker compose down` loses nothing. To start from an empty database, stop the
container and delete `data/cyclone.db*`.

## Changing the frontend

The image does not run Node. It uses the committed `frontend/assets/verification.js`.
After editing `frontend/src/verification.ts`, run `npm run build` in
`frontend/` (see the main README), commit the updated `frontend/assets/verification.js`,
then rebuild the image.

## Troubleshooting

- **`startup.sh: line 2: $'\r': command not found`** — the script has Windows
  (CRLF) line endings. `.gitattributes` forces LF, so re-checkout the file:
  `git rm --cached startup.sh && git checkout -- startup.sh`, or convert it
  with `dos2unix`.
- **Map or verification pages are empty** — `data/` is missing or has not been
  processed; follow [Loading the data](#loading-the-data).
- **Basemap shows an "API KEY REQUIRED" watermark** — set `CARTO_API_KEY` in
  `.env` and run `docker compose up -d` again.
- **Port 8000 already in use** — change the host side of `ports:`.
- **`unable to open database file`** — the `data` folder is not mounted or is
  not writable. Check the `-v` / `volumes:` path and, on Linux, its ownership.
- **Build is slow or the build context is huge** — make sure `.dockerignore`
  is present; it keeps `data/` (about 1.6 GB) and `.git` out of the image.
