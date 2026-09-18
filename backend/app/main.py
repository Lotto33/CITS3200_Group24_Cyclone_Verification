"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, settings

VIEWER_PAGE = PROJECT_ROOT / "visualize.html"

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


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/visualize.html")


@app.get("/visualize.html", include_in_schema=False)
def visualize() -> FileResponse:
    """The Leaflet viewer. Its data still comes from the build_*.py JSON."""
    return FileResponse(VIEWER_PAGE, media_type="text/html")


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Basic liveness probe."""
    return {"status": "ok"}
