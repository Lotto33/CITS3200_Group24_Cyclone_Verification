import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

from app.core.config import settings

DATA_DIR = settings.DATA_DIR

@router.get("/map")
def get_map_config():
    path = DATA_DIR / "map_config.json"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Map configuration not found"
        )

    with path.open() as f:
        return json.load(f)