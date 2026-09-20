from fastapi import APIRouter, HTTPException

from app.services import town_service

router = APIRouter()


@router.get("/")
def get_towns():
    return town_service.get_towns()

@router.get("/{town}")
def get_town(town:str):
    try:
        return town_service.get_town(town)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Town not found: {town}") from exc