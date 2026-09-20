"""Aggregates all v1 endpoint routers into a single APIRouter."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    bulletins,
    codes,
    contingency,
    cyclones,
    datasets,
    diagnostics,
    disturbances,
    towns,
    verification,
    config,
)

api_router = APIRouter()
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(
    contingency.router, prefix="/contingency-tables", tags=["contingency tables"]
)
api_router.include_router(cyclones.router, prefix="/cyclones", tags=["cyclones"])
api_router.include_router(towns.router, prefix="/towns", tags=["towns"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(diagnostics.router, prefix="/diagnostics", tags=["diagnostics"])
api_router.include_router(
    disturbances.router, prefix="/disturbances", tags=["disturbances"]
)
api_router.include_router(bulletins.router, prefix="/bulletins", tags=["bulletins"])
api_router.include_router(codes.router, prefix="/codes", tags=["codes"])
api_router.include_router(
    verification.router, prefix="/verification-runs", tags=["verification"]
)
