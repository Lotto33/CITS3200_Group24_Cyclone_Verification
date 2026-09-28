import json
from pathlib import Path

from app.core.config import settings


def get_all_cyclones():
    path = settings.DATA_DIR / "index.json"
    if not path.is_file():
        return {"regions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def get_cyclone(region: str, dist_id: str):
    path = settings.DATA_DIR / region / f"{dist_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Cyclone dataset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_best_track(dist_id: str):
    path = settings.DATA_DIR / "best_track" / f"{dist_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Best-track dataset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))