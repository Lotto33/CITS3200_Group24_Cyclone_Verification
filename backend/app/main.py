"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""

import subprocess
import sys
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, settings

VIEWER_PAGE = PROJECT_ROOT / "visualize.html"
VERIFICATION_PAGE = PROJECT_ROOT / "verification.html"
ASSETS_DIR = PROJECT_ROOT / "assets"
BACKEND_DIR = PROJECT_ROOT / "backend"

_initialization_lock = threading.Lock()
_initialization_started = False
_initialization_status = "not started"


def _initialize_backend() -> None:
    """Run the documented database setup once for this server process."""
    global _initialization_status
    try:
        for command in (
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            [sys.executable, "-m", "app.cli", "all"],
        ):
            subprocess.run(command, cwd=BACKEND_DIR, check=True)
        _initialization_status = "complete"
    except Exception as exc:  # noqa: BLE001 - report status to the homepage
        _initialization_status = f"failed: {exc}"

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


@app.post("/initialize", tags=["startup"])
def initialize() -> dict[str, str]:
    """Start the one-time schema and data initialization requested by the homepage."""
    global _initialization_started, _initialization_status
    with _initialization_lock:
        if not _initialization_started:
            _initialization_started = True
            _initialization_status = "running"
            threading.Thread(target=_initialize_backend, daemon=True).start()
            return {"status": "running", "message": "Backend initialization started."}
    return {"status": _initialization_status, "message": "Backend initialization already started."}


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
