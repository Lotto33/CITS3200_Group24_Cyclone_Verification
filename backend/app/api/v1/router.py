"""Aggregates all v1 endpoint routers into a single APIRouter."""

from fastapi import APIRouter

from app.api.v1.endpoints import cyclones, datasets, towns, config

api_router = APIRouter()


api_router.include_router(datasets.router,prefix="/datasets",tags=["datasets"])

api_router.include_router(datasets.router,prefix="/cyclones",tags=["cyclones"])

api_router.include_router(datasets.router,prefix="/towns",tags=["towns"])

api_router.include_router(datasets.router,prefix="/config",tags=["config"])