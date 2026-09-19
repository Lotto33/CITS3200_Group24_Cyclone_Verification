from fastapi import APIRouter
from app.services import cyclone_service
router = APIRouter()

@router.get("/cyclones")
def get_cyclones():
    return cyclone_service.get_all_cyclones()

# I don't think time is a required parameter here. 
@router.get("/{state}/{dist_id}")
def get_cyclone(state:str, dist_id:str):
    return cyclone_service.get_cyclone(state, dist_id) 

@router.get("/{dist_id}/best-track")
def get_best_track(dist_id: str):
    return cyclone_service.get_best_track(dist_id)