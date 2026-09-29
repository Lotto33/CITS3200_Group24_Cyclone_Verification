"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, settings
from app.db.session import engine

VIEWER_PAGE = PROJECT_ROOT / "visualize.html"
VERIFICATION_PAGE = PROJECT_ROOT / "verification.html"
ASSETS_DIR = PROJECT_ROOT / "assets"

_READINESS_TABLES = (
    "disturbance",
    "best_track_observation",
    "bulletin",
    "town",
    "interpolation_run",
    "verification_run",
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

# visualize.html is served by this app (below), so it needs no CORS. This is
# for viewers still served from another origin, e.g. python -m http.server.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# visualize.html fetches its JSON with relative "data/..." URLs, so the page
# must sit at the root and data/ must be mounted beside it at /data.
# check_dir=False: data/ is git-ignored, and a fresh clone should still boot.
app.mount(
    "/data",
    StaticFiles(directory=settings.DATA_DIR, check_dir=False),
    name="data",
)

# The pages' CSS and JS were split out of the HTML into assets/, and both
# reference it as a relative "assets/..." URL, so it mounts at /assets.
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "homepage.html", media_type="text/html")


@app.get("/initialize", tags=["startup"])
def initialize() -> dict:
    """Report database readiness without changing the database."""
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
            row_counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _READINESS_TABLES
            }
    except SQLAlchemyError:
        return {
            "status": "not ready",
            "message": "Database is not ready.",
        }

    return {
        "status": "ready",
        "revision": revision,
        "row_counts": row_counts,
        "message": "Database is ready.",
    }


@app.get("/visualize.html", include_in_schema=False)
def visualize() -> FileResponse:
    """The Leaflet viewer. Its bulletins still come from the build_*.py JSON;
    only the best-track overlay reads this app's /api/v1."""
    return FileResponse(VIEWER_PAGE, media_type="text/html")


@app.get("/verification.html", include_in_schema=False)
def verification() -> FileResponse:
    """The contingency-table page the viewer links to."""
    return FileResponse(VERIFICATION_PAGE, media_type="text/html")


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Basic liveness probe."""
    return {"status": "ok"}
