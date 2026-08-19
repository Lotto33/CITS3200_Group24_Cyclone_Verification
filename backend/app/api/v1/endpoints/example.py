"""Example endpoint module — copy this pattern for real resources.

Delete once real endpoint modules (e.g. `cyclones.py`) exist, and wire
them into `app.api.v1.router` the same way.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping() -> dict:
    return {"ping": "pong"}
