from fastapi import APIRouter, UploadFile

from app.services import dataset_service

router = APIRouter()


@router.post("/")
def create_dataset():
    return dataset_service.build_dataset()


@router.get("/status")
def dataset_status():
    return dataset_service.get_status()