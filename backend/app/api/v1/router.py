"""Aggregates all v1 endpoint routers into a single APIRouter."""

from fastapi import APIRouter

from app.api.v1.endpoints import example

api_router = APIRouter()
api_router.include_router(example.router, prefix="/example", tags=["example"])
