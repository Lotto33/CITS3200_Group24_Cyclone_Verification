from fastapi import APIRouter

from app.services import town_service

router = APIRouter()


@router.get("/")
def get_towns():
    return town_service.get_towns()

@router.get("/{town}")
def get_town(town:str):
    return town_service.get_town(town)