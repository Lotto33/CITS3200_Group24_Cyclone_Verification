from fastapi import APIRouter, HTTPException
from app.services import cyclone_service
router = APIRouter()

@router.get("/")
def get_cyclones():
    return cyclone_service.get_all_cyclones()

@router.get("/{region}/{dist_id}")
def get_cyclone(region: str, dist_id: str):
    try:
        return cyclone_service.get_cyclone(region, dist_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/{dist_id}/best-track")
def get_best_track(dist_id: str):
    try:
        return cyclone_service.get_best_track(dist_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc